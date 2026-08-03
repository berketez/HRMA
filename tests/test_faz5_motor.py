"""Faz 5B — motor tarafı bulgularının bekçileri.

Bu dosyadaki her test, Faz 5 avında ÖLÇÜLEN somut bir kusurun geri
gelmesini engeller. Her testin docstring'inde düzeltme ÖNCESİ ölçüm yazar;
sayı uydurulmamıştır, hepsi 3 Ağustos 2026'da bu depoda koşturularak
alınmıştır.

Kapsanan bulgular:
  H5-1  RocketCEA veri dizini süreçler arası paylaşımlıydı -> eşzamanlı
        süreç Fortran EOF ile ölüyordu; iş parçacıkları COMMON bloklarını
        ezip sessizce yanlış sayı üretiyordu.
  H2-2  Sıvı irtifa haritasında işaret ters dönmesi ve kutup (negatif Isp).
  H2-3  CEA önbelleği yalnız TAM SAYI bar çözünürlüğündeydi (c* basamaklı).
  H2-4  Katalog yakıtında kullanılmayan a/n yanıtta geri yayımlanıyordu.
  H2-5  mixture_ratio_efficiency %100'ü aşıyordu.
  H4-7  Aynı motorun iki kuru kütlesi; otorite beyan edilmiyordu.
  H4-8  Kasa MALİYETİ ile kasa KÜTLESİ farklı malzeme/kalınlık kullanıyordu.
  H4-9  "chamber_volume" üç anlam, iki birim; motor tarafı beyansızdı.
  H4-11 Kelvin -> Celsius çevriminde 273 (273,15 olmalı).
"""

import os
import threading

import pytest

pytestmark = pytest.mark.filterwarnings('ignore::RuntimeWarning')


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------
def _quiet(fn, *args, **kwargs):
    """Motor modülleri stdout'a bolca basıyor; testte sessize al."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


SOLID_BASE = {
    'motor_name': 'faz5', 'chamber_pressure': 40, 'thrust': 1500,
    'burn_time': 3, 'grain_type': 'bates', 'outer_diameter': 100,
    'core_diameter': 35, 'grain_length': 300, 'segments': 1,
    'burn_rate_a': 0.005, 'burn_rate_n': 0.35, 'chamber_temperature': 3000,
    'c_star': 1550, 'propellant_density': 1800,
}


def _post_solid(client, **degisim):
    payload = dict(SOLID_BASE)
    payload.setdefault('propellant_type', 'apcp')
    payload.update(degisim)
    resp = _quiet(client.post, '/calculate_solid', json=payload)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    body = resp.get_json()
    assert not body.get('error'), body.get('error')
    return body


# ---------------------------------------------------------------------------
# H5-1 — RocketCEA süreç yalıtımı + iş parçacığı güvenliği
# ---------------------------------------------------------------------------
class TestCeaProcessIsolation:
    """Ölçüm (düzeltme ÖNCESİ, 3 Ağustos 2026):

    * 6 eşzamanlı SÜREÇ x 120 CEA çağrısı -> 2 süreç `exit=2` ile öldü:
      "At line 5462 of file ../rocketcea/py_cea.f (unit = 13, file =
       '/Users/apple/RocketCEA/temp.dat') Fortran runtime error: End of file"
      Fortran çalışma zamanı hatası Python istisnası değildir; süreç
      traceback bırakmadan ölür ve `except` ile yakalanamaz.
    * 6 eşzamanlı İŞ PARÇACIĞI x 36 çağrı -> çökme yok ama Fortran
      "Bad Solution in CalcPCoPE ... input gam= 0.0" bastı (sessizce yanlış
      sayı). Aynı iş yükü tek iş parçacığında 0 uyarı veriyordu.

    Düzeltme SONRASI: 6/6 süreç exit=0 (720/720 çağrı), iş parçacığı
    koşusunda 0 uyarı.
    """

    def test_data_dir_is_process_local(self):
        cea = pytest.importorskip('rocketcea.cea_obj')
        from hrma.engines import cea_bridge
        yol = cea_bridge.ensure_isolated_cea_data_dir()
        assert yol, 'CEA veri dizini bu sürece sabitlenemedi'
        varsayilan = os.path.join(
            os.path.dirname(os.path.expanduser('~/')), 'RocketCEA')
        assert os.path.normpath(yol) != os.path.normpath(varsayilan), (
            'CEA hâlâ kullanıcı başına SABİT dizini kullanıyor: iki HRMA '
            'süreci aynı temp.dat üstünde çalışır ve Fortran EOF ile ölür.')
        assert str(os.getpid()) in yol, (
            'Yalıtılmış dizin adı süreç kimliğini taşımıyor; iki süreç aynı '
            'dizine düşebilir.')
        assert os.path.normpath(cea.ROCKETCEA_DATA_DIR) == \
            os.path.normpath(yol), (
            'rocketcea.cea_obj modülünün global veri dizini sabitlenmemiş; '
            'CEA_Obj pathPrefix\'i eski dizinden alır.')

    def test_second_call_is_idempotent(self):
        pytest.importorskip('rocketcea.cea_obj')
        from hrma.engines import cea_bridge
        assert cea_bridge.ensure_isolated_cea_data_dir() == \
            cea_bridge.ensure_isolated_cea_data_dir()

    def test_cea_calls_are_serialised_within_the_process(self):
        """py_cea COMMON blokları paylaşımlı; eşzamanlı çağrı serileşmeli."""
        pytest.importorskip('rocketcea.cea_obj')
        from hrma.engines import cea_bridge
        assert isinstance(cea_bridge._CEA_STATE_LOCK,
                          type(threading.RLock())), (
            'CEA çağrıları için süreç içi kilit yok.')

        hatalar = []
        sonuclar = {}

        def calis(ofs):
            try:
                for k in range(4):
                    r = cea_bridge.get_combustion_properties(
                        fuel='rp1', oxidizer='lox', pc_bar=45.0 + k,
                        mr=2.4, expansion_ratio=12.0 + k, fallback={})
                    sonuclar[(ofs, k)] = r['c_star_m_s']
            except Exception as exc:      # pragma: no cover - regresyon ağı
                hatalar.append(repr(exc))

        isler = [threading.Thread(target=calis, args=(i,)) for i in range(4)]
        for t in isler:
            t.start()
        for t in isler:
            t.join()
        assert not hatalar, hatalar
        # Aynı (Pc, MR, eps) noktası hangi iş parçacığından gelirse gelsin
        # BİT-AYNI olmalı; çöplenmiş COMMON bloğu bunu bozar.
        for k in range(4):
            degerler = {sonuclar[(ofs, k)] for ofs in range(4)}
            assert len(degerler) == 1, (
                'Aynı çalışma noktası iş parçacığına göre farklı c* verdi: '
                '%r' % (degerler,))
            assert all(v is None or v > 0 for v in degerler)


# ---------------------------------------------------------------------------
# H2-3 — CEA önbellek çözünürlüğü: c* Pc ile SÜREKLİ olmalı
# ---------------------------------------------------------------------------
class TestCeaPressureResolution:
    """Ölçüm (düzeltme ÖNCESİ, `_PC_ROUND = 0`):

        Pc=70.00  c_star=1810.060493
        Pc=70.20  c_star=1810.060493   <- bit-aynı
        Pc=70.40  c_star=1810.060493   <- bit-aynı
        Pc=70.50  c_star=1810.060493   <- bit-aynı
        Pc=70.60  c_star=1810.277025   <- süreksiz sıçrama

    Yani yarım bar genişliğinde bir düzlük. Düzeltme SONRASI aynı tarama
    kesin artan ve süreklidir (1810.060 / 1810.104 / 1810.148 / 1810.169 /
    1810.191).
    """

    def test_cstar_responds_to_sub_bar_pressure_changes(self):
        pytest.importorskip('rocketcea.cea_obj')
        from hrma.engines.cea_bridge import get_combustion_properties
        basinclar = (70.0, 70.2, 70.4, 70.6, 70.8)
        c = [_quiet(get_combustion_properties, 'rp1', 'lox', p, 2.3,
                    expansion_ratio=25.0, fallback={})['c_star_m_s']
             for p in basinclar]
        assert all(v is not None for v in c), 'CEA çözemedi'
        assert len(set(c)) == len(c), (
            'Yarım bar bandında c* SABİT kaldı — Pc nicemlemesi çözümün '
            'duyarlılığından kaba: %r' % (c,))
        assert all(c[i] < c[i + 1] for i in range(len(c) - 1)), (
            'c* oda basıncıyla monoton artmadı: %r' % (c,))

    def test_significant_digit_rounding_is_relative(self):
        from hrma.engines.cea_bridge import _round_significant
        assert _round_significant(70.5000000000001, 6) == 70.5
        assert _round_significant(10.49, 6) == 10.49
        assert _round_significant(0.0, 6) == 0.0
        # Bağıl çözünürlük: 10 bar ve 500 bar'da aynı BAĞIL adım.
        assert _round_significant(123.456789, 6) == 123.457
        assert _round_significant(0.000123456789, 6) == pytest.approx(
            0.000123457, rel=1e-12)


# ---------------------------------------------------------------------------
# H2-2 — Sıvı irtifa haritası: işaret ters dönmesi ve kutup
# ---------------------------------------------------------------------------
# Motorun KENDİ irtifa listesi (liquid_rocket_engine.calculate_performance
# içindeki tarama ile aynı noktalar). Ad, başka test dosyalarındaki
# ALTITUDES sabitiyle çakışmasın diye ayrı tutulur.
IRTIFA_NOKTALARI = [0, 1000, 5000, 10000, 20000, 50000, 80000, 100000]


def _liquid_engine(**ov):
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    overrides = {'nozzle_type': 'bell_80', 'contraction_ratio': 4,
                 'characteristic_length': 1.2}
    overrides.update(ov)
    motor = _quiet(
        LiquidRocketEngine, thrust=25000, chamber_pressure=70,
        mixture_ratio=2.3, fuel_type='rp1', oxidizer_type='lox',
        cooling_type='regenerative', injector_type='impinging',
        overrides=overrides)
    _quiet(motor.calculate_performance)
    return motor


@pytest.fixture(scope='module')
def wide_nozzle_map():
    pytest.importorskip('rocketcea.cea_obj')
    motor = _liquid_engine(nozzle_expansion_ratio=250.0)
    return motor, _quiet(motor.calculate_altitude_performance, IRTIFA_NOKTALARI)


@pytest.fixture(scope='module')
def attached_nozzle_map():
    pytest.importorskip('rocketcea.cea_obj')
    motor = _liquid_engine(nozzle_expansion_ratio=12.0)
    return motor, _quiet(motor.calculate_altitude_performance, IRTIFA_NOKTALARI)


class TestAltitudeIspSign:
    """Ölçüm (düzeltme ÖNCESİ, 25 kN LOX/RP-1, Pc=70 bar):

        epsilon   Isp@50km (s)   itki@50km (kN)   CF@50km
            135          356.1             34.6     1.891
            138    -2 029 819.0       -197 247.8  -10777.3
            140        -18 120.0         -1 761.5     -96.2
            250           -320.5            -31.9      -1.7

    Kök neden: `isp_altitude = isp_sl * CF_ideal / CF_ideal_sl`. Aşırı
    genişlemiş lülede CF_ideal_sl sıfırı geçip negatife dönüyor (ε=138'de
    -0,0003), oran önce patlıyor sonra işaret değiştiriyor. HTTP 200 ve
    `error` alanı boştu.
    """

    def test_no_negative_specific_impulse_or_thrust(self, wide_nozzle_map):
        _motor, veri = wide_nozzle_map
        for satir in veri:
            for alan in ('specific_impulse', 'thrust', 'thrust_coefficient'):
                deger = satir[alan]
                assert deger is None or deger > 0.0, (
                    'h=%s m: %s = %r — negatif itki/Isp yayımlanamaz'
                    % (satir['altitude'], alan, deger))

    def test_isp_never_exceeds_the_vacuum_reference(self, wide_nozzle_map):
        motor, veri = wide_nozzle_map
        for satir in veri:
            isp = satir['specific_impulse']
            if isp is not None:
                assert isp <= motor.isp_vac * (1.0 + 1e-9), (
                    'h=%s m: Isp=%r CEA vakum referansını (%r) aştı'
                    % (satir['altitude'], isp, motor.isp_vac))

    def test_isp_increases_with_altitude(self, wide_nozzle_map):
        _motor, veri = wide_nozzle_map
        cozulen = [(s['altitude'], s['specific_impulse']) for s in veri
                   if s['specific_impulse'] is not None]
        assert len(cozulen) >= 3, 'İrtifa haritasının çoğu çözülemedi'
        for (h0, i0), (h1, i1) in zip(cozulen, cozulen[1:]):
            assert i1 >= i0 - 1e-9, (
                'Isp irtifayla azaldı: %s m -> %.3f s, %s m -> %.3f s'
                % (h0, i0, h1, i1))

    def test_unsolved_rows_declare_why(self, wide_nozzle_map):
        _motor, veri = wide_nozzle_map
        cozulmeyen = [s for s in veri if s['specific_impulse'] is None]
        assert cozulmeyen, (
            'ε=250 lüle deniz seviyesinde ayrılmış olmalı; bu koşuda hiçbir '
            'satır NOT_MODELLED işaretlenmedi — model ayrılmayı çözmüyor.')
        for satir in cozulmeyen:
            assert satir['not_modelled_reason'], (
                'h=%s m çözülemedi ama gerekçesi yok' % satir['altitude'])
            assert satir['thrust'] is None and satir['isp_ratio'] is None

    def test_anchor_is_declared(self, wide_nozzle_map, attached_nozzle_map):
        _m1, genis = wide_nozzle_map
        _m2, dar = attached_nozzle_map
        assert 'vacuum reference' in genis[0]['isp_anchor_basis'], (
            'Ayrılmış lülede demir vakuma taşınmadı: %r'
            % genis[0]['isp_anchor_basis'])
        assert 'sea-level design point' in dar[0]['isp_anchor_basis'], (
            'Bağlı akışta deniz seviyesi demiri korunmalıydı: %r'
            % dar[0]['isp_anchor_basis'])

    def test_sea_level_thrust_still_matches_the_commanded_thrust(
            self, attached_nozzle_map):
        """Ayrılma YOKKEN eski sözleşme birebir korunmalı (regresyon ağı).

        Ölçüm: ε=12'de h=0 satırı hem düzeltme öncesi hem sonrası
        Isp = 286,030 s ve itki = 25,000 kN veriyor.
        """
        motor, veri = attached_nozzle_map
        assert veri[0]['altitude'] == 0
        assert veri[0]['specific_impulse'] == pytest.approx(
            motor.isp_sl, rel=1e-9)
        assert veri[0]['thrust'] == pytest.approx(motor.F, rel=1e-6)

    def test_performance_map_arrays_survive_unsolved_rows(self):
        """`float(None)` çökmesi olmamalı; boşluk None olarak taşınır."""
        pytest.importorskip('rocketcea.cea_obj')
        motor = _liquid_engine(nozzle_expansion_ratio=250.0)
        haritalar = _quiet(motor._generate_performance_optimization_maps)
        alt = haritalar['altitude_performance']
        isp = alt['isp_vs_altitude']
        assert len(isp) == len(alt['altitude_range'])
        assert any(v is not None for v in isp), 'Tüm irtifa haritası boş'
        for v in isp + alt['thrust_vs_altitude']:
            assert v is None or v > 0.0, 'Haritada negatif değer var: %r' % v


# ---------------------------------------------------------------------------
# H2-5 — mixture_ratio_efficiency %100'ü aşamaz
# ---------------------------------------------------------------------------
class TestMixtureRatioEfficiency:
    """Ölçüm (düzeltme ÖNCESİ, Pc=11 bar LOX/RP-1 O/F=2,3):
    `mixture_ratio_efficiency = 100.02585694901296`. Tanım "seçilen O/F'nin
    Isp'si / bu taramanın maksimumu" olduğu için <= %100 olmalıydı; eşit
    aralıklı ızgara seçilen O/F'yi içermiyordu.
    Düzeltme SONRASI: %99,9175611455.
    """

    @pytest.mark.parametrize('pc', [11, 20, 70])
    def test_efficiency_stays_within_its_own_definition(self, client, pc):
        pytest.importorskip('rocketcea.cea_obj')
        yuk = {'fuel_type': 'rp1', 'oxidizer_type': 'lox',
               'mixture_ratio': 2.3, 'thrust': 25000,
               'chamber_pressure': pc, 'engine_cycle': 'gas_generator',
               'injector_type': 'impinging', 'contraction_ratio': 4,
               'characteristic_length': 1.2,
               'chamber_material': 'inconel_718',
               'cooling_type': 'regenerative', 'nozzle_type': 'bell_80',
               'safety_factor': 2.5}
        resp = _quiet(client.post, '/calculate_liquid', json=yuk)
        assert resp.status_code == 200
        govde = resp.get_json()
        eta = govde['mixture_ratio_efficiency']
        assert eta is not None and eta <= 100.0 + 1e-9, (
            'O/F verimi kendi tanımını aştı: %r' % eta)
        harita = govde['performance_maps']['mixture_ratio_optimization']
        assert any(abs(m - harita['current_mr']) < 1e-9
                   for m in harita['mr_range']), (
            'Seçilen O/F taramanın kendi ızgarasında yok; oran yine '
            '%100 üstüne çıkabilir.')


# ---------------------------------------------------------------------------
# H2-4 — Katalog yakıtında kullanılmayan a/n geri yayımlanamaz
# ---------------------------------------------------------------------------
class TestBurnRateEcho:
    """Ölçüm (düzeltme ÖNCESİ, kndx, Pc=30 bar, aynı geometri):
        n=0.200 -> isp=138.1603514622613  burn_time=1.8649276127370293
        n=0.688 -> isp=138.1603514622613  burn_time=1.8649276127370293
        n=0.950 -> isp=138.1603514622613  burn_time=1.8649276127370293
    yani 15 anlamlı basamak aynı; buna rağmen yanıt kullanıcının n'ini
    `burn_rate_exponent` alanında geri yayımlıyordu.
    """

    def test_catalogue_fuel_does_not_republish_the_unused_pair(self, client):
        govde = _post_solid(client, propellant_type='kndx',
                            burn_rate_a=0.0007876, burn_rate_n=0.95)
        assert govde['burn_rate_coefficient'] is None
        assert govde['burn_rate_exponent'] is None
        assert govde['burn_rate_exponent_input'] == 0.95
        assert govde['burn_rate_coefficient_input'] == 0.0007876
        assert 'NOT used' in govde['burn_rate_basis']
        yasa = govde['burn_rate_law']
        assert yasa and yasa['key'] == 'kndx' and yasa['regimes'], (
            'Gerçekten kullanılan rejim tablosu yayımlanmıyor.')
        beyan = [alan for grup in govde['unwired_inputs'].values()
                 for alan in (grup or [])]
        assert 'burn_rate_exponent' in beyan and \
            'burn_rate_coefficient' in beyan

    def test_catalogue_fuel_result_really_ignores_the_pair(self, client):
        sonuc = [_post_solid(client, propellant_type='kndx',
                             burn_rate_n=n)['burn_time'] for n in (0.2, 0.95)]
        assert sonuc[0] == sonuc[1], (
            'Beyan ile davranış çelişiyor: a/n "kullanılmıyor" deniyor ama '
            'sonuç değişti (%r)' % (sonuc,))

    def test_off_catalogue_fuel_keeps_the_pair_live(self, client):
        govde = _post_solid(client, propellant_type='ozel_karisim',
                            burn_rate_n=0.35)
        assert govde['burn_rate_exponent'] == 0.35
        assert govde['burn_rate_coefficient'] is not None
        assert govde['burn_rate_law'] is None
        beyan = [alan for grup in govde['unwired_inputs'].values()
                 for alan in (grup or [])]
        assert 'burn_rate_exponent' not in beyan, (
            'Alan canlı olduğu hâlde "kullanılmıyor" diye bildiriliyor '
            '(beyan çürümesi).')
        sureler = [_post_solid(client, propellant_type='ozel_karisim',
                               burn_rate_n=n)['burn_time']
                   for n in (0.2, 0.688)]
        assert sureler[0] != sureler[1]


# ---------------------------------------------------------------------------
# H4-8 — Kasa maliyeti ile kasa kütlesi aynı kaynaktan beslenmeli
# ---------------------------------------------------------------------------
class TestCaseCostMassConsistency:
    """Ölçüm (düzeltme ÖNCESİ):

        case_material     kütle ρ   maliyet ρ   $/kg   kasa $
        (yok)               7800      2700       15     32,9
        steel_4130          7800      2700       15     32,9
        titanium_6al4v      4430      2700       15     32,9

    Katalog anahtarı verilen HER durumda maliyet modeli sessizce
    ALÜMİNYUMA düşüyordu; cidar da ayrıydı (0,045·D = 4,5 mm, yapısal
    analiz 2,4 mm). Titanyum kasa 9,8 kat ucuz fiyatlanıyordu.
    """

    def test_case_cost_tracks_the_selected_material(self, client):
        fiyat = {}
        for malzeme in ('steel_4130', 'titanium_6al4v', 'composite',
                        'aluminum'):
            govde = _post_solid(client, case_material=malzeme)
            kalem = govde['cost_analysis']['material_costs_usd']
            fiyat[malzeme] = kalem['case_materials']
            assert kalem['case_materials'] is not None
        assert len(set(fiyat.values())) == len(fiyat), (
            'Farklı kasa malzemeleri aynı fiyatı verdi: %r' % (fiyat,))
        assert fiyat['titanium_6al4v'] > fiyat['steel_4130'], (
            'Titanyum kasa çelikten ucuz fiyatlanıyor: %r' % (fiyat,))

    def test_case_mass_matches_the_structural_chain(self, client):
        from hrma.engines.solid_rocket_engine import (
            SOLID_CASE_CLOSURE_MASS_FRACTION, SolidRocketEngine)
        import numpy as np
        govde = _post_solid(client, case_material='steel_4130')
        kalem = govde['cost_analysis']['material_costs_usd']

        motor = _quiet(
            SolidRocketEngine, grain_type='bates', propellant_type='apcp',
            chamber_diameter=100, grain_length=300, core_diameter=35,
            chamber_pressure=40, burn_rate_a=0.005, burn_rate_n=0.35,
            overrides={'thrust': 1500, 'burn_time': 3, 'segments': 1,
                       'outer_diameter': 100, 'chamber_temperature': 3000,
                       'c_star': 1550, 'propellant_density': 1800,
                       'case_material': 'steel_4130'})
        _malzeme, _sy, _sf, t_wall = motor._case_design()
        beklenen = (np.pi * motor._case_inner_diameter()
                    * motor._case_inner_length() * t_wall
                    * motor._case_density()
                    * (1.0 + SOLID_CASE_CLOSURE_MASS_FRACTION))
        assert kalem['case_mass_kg'] == pytest.approx(beklenen, rel=1e-3), (
            'Maliyet modelinin kasa kütlesi yapısal zincirle uyuşmuyor: '
            '%r != %r' % (kalem['case_mass_kg'], beklenen))
        assert '_case_design' in kalem['case_cost_basis']

    def test_unpriced_material_is_declared_not_substituted(self, client):
        govde = _post_solid(client, case_material='inconel_718')
        kalem = govde['cost_analysis']['material_costs_usd']
        assert kalem['case_materials'] is None
        assert kalem['total_materials'] is None
        assert 'not_priced' in kalem['case_cost_basis']
        assert govde['cost_analysis']['cost_per_flight'][
            'recurring_cost_usd'] is None, (
            'Kasa fiyatlanamadığı hâlde eksik bir toplam "tekrarlayan '
            'maliyet" diye yayımlanıyor.')


# ---------------------------------------------------------------------------
# H4-11 — Kelvin -> Celsius çevrimi 273,15 ile
# ---------------------------------------------------------------------------
def test_curing_temperature_celsius_uses_273_15(client):
    """Arayüz `v => v - 273` yapıyordu; sunucu doğru sabitle yayımlar."""
    govde = _post_solid(client)
    kur = govde['manufacturing_analysis'][
        'propellant_manufacturing']['curing_process']
    assert kur['temperature_c'] == pytest.approx(
        kur['temperature_k'] - 273.15, abs=1e-9)
    assert kur['temperature_c'] != pytest.approx(
        kur['temperature_k'] - 273.0, abs=1e-9)


# ---------------------------------------------------------------------------
# H4-7 / H4-9 — Hibrit: kuru kütle otoritesi ve kamara hacmi beyanı
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def hybrid_result(client):
    yuk = {'motor_name': 'faz5h', 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
           'thrust': 2000, 'burn_time': 10, 'chamber_pressure': 30,
           'of_ratio': 6.0}
    resp = _quiet(client.post, '/calculate', json=yuk)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()


def _bul(kok, anahtar):
    """İç içe sözlükte ilk eşleşen anahtarın değerini döndürür."""
    yigin = [kok]
    while yigin:
        dugum = yigin.pop(0)
        if isinstance(dugum, dict):
            if anahtar in dugum:
                return dugum[anahtar]
            yigin.extend(dugum.values())
        elif isinstance(dugum, list):
            yigin.extend(dugum)
    return None


def test_dry_mass_declares_its_authority_and_scope(hybrid_result):
    """Ölçüm: aynı yanıtta iki "kuru kütle" var ve %22,8 ayrışıyorlar
    (structural 16,8366 kg / CAD 13,7130 kg). Hangisinin uçuş zincirine
    gittiği hiçbir yerde yazmıyordu."""
    temel = _bul(hybrid_result, 'dry_mass_basis')
    assert temel, 'dry_mass_basis yayımlanmıyor'
    assert 'AUTHORITATIVE' in temel
    assert 'injector is NOT included' in temel or 'injector' in temel
    assert 'mass_breakdown' in temel, (
        'İkinci toplamın varlığı beyan edilmiyor; kullanıcı iki farklı '
        'kuru kütleyi karşılaştıramaz.')
    assert _bul(hybrid_result, 'dry_mass_estimate_kg') is not None


def test_chamber_volume_declares_meaning_and_unit(hybrid_result):
    """Ölçüm: `chamber_volume` 731,6 cm³ (tasarım hedefi),
    `chamber_volume_actual` 3221,5 cm³ (gerçek serbest hacim) ve CAD
    tarafında 8011,58 cm³ (brüt silindir) — üçü de aynı adla."""
    motor = hybrid_result.get('motor', hybrid_result)
    assert motor['chamber_volume_m3'] == motor['chamber_volume']
    assert motor['chamber_volume_actual_m3'] == motor['chamber_volume_actual']
    hedef = motor['chamber_volume_basis']
    gercek = motor['chamber_volume_actual_basis']
    assert 'DESIGN TARGET' in hedef and 'm^3' in hedef
    assert 'ACTUAL free volume' in gercek and 'm^3' in gercek
    assert motor['chamber_volume_actual'] > 0 and motor['chamber_volume'] > 0
