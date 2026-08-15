"""v2.6.27 / B4 — sıvı motorun bağlama ve beyan bekçileri.

Bu dosya dört işi kilitler. Hepsi bu depoda ÖLÇÜLDÜ (11 Ağustos 2026);
testler ölçümün kendisini değil, ölçümün gösterdiği DOĞRU SÖZLEŞMEYİ korur.

**KALEM 1 — bağlamanın testi yoktu.** Önceki dalgada sıvı motora dört blok
bağlandı (``_feed_fluid_record``, ``_turbopump_sizing_block`` [C1],
``_valve_feedline_block`` [C2], ``_passive_thermal_protection`` [A5]) ama
hiçbiri testle korunmuyordu. Burada her blok İKİ YÖNLÜ ölçülür: koşul
sağlandığında alan gerçekten çıkıyor mu, sağlanmadığında BEYAN çıkıp
UYDURMA SAYI çıkmıyor mu. İkincisi birincisinden önemlidir — bir bloğun
sessizce sayı üretmesi, hiç üretmemesinden kötüdür.

Bu kalemin içinde bir KUSUR da bulundu ve düzeltildi: A5 bloğunun
"modelled" dalı sonucu ÇIPLAK döndürüyor, çağıran da ``result.update()``
ile onu ısıl koruma sözlüğünün köküne serpiyordu. Sonuç: sizing'in
GERÇEKTEN yapıldığı ablatif/radyatif koşuda ``passive_thermal_protection``
adresi HİÇ yoktu (rejeneratifte NOT_APPLICABLE olarak vardı),
``cooling_type`` 'Ablative' iken 'ablative' ile eziliyordu ve astara ait
``status: modelled`` ısıl koruma bloğunun köküne çıkıyordu. Test doğru
sözleşmeyi (üç dalın da aynı adreste yayımlanması) kilitler.

**KALEM 2 — yapısal beyan eksiği.** Tank bloğu emniyet katsayısının
kaynağını beyan ediyordu; HAZNE tarafında aynı beyan yoktu. Ölçüldü: hiçbir
şey göndermeden ``structural_analysis.chamber_structure`` şunu diyordu::

    safety_factor : 2.5
    material      : 'Inconel 718 (aged)'

İkisi de varsayılandı ama çıktıda kullanıcı seçiminden ayırt edilemiyordu.
Üstelik tankın künyesi yalnız anahtarın gövdede BULUNMASINA bakıyordu:
aralık dışı bir katsayı (99) gönderildiğinde değer reddedilip 2,5
kullanılıyor, künye ise hâlâ "user input (safety factor)" diyordu.

**KALEM 3 — ``expansion_ratio`` gövdeden hiç okunmuyor.** Ölçüldü: bu ada
4 / 20 / 60 / 150 / 400 gönderildi, BEŞİNDE DE yanıt
``expansion_ratio = 13,223420430204907`` ve ``isp_sea_level = 298,37``
döndü. Sıvı çözücünün girdi adı ``nozzle_expansion_ratio``'dur;
``expansion_ratio`` ise çözücünün ÜRETTİĞİ çıktı adıdır. Alan takma ad
yapılmadı (gerekçesi ``LIQUID_UNREAD_INPUT_FIELDS`` yorumunda: sonucu geri
gönderen istemci lüleyi sessizce sabitlerdi); bunun yerine depodaki mevcut
``inputs_not_used`` beyanı motor tarafında da üretilir ve DOĞRU alan adı
söylenir.

**KALEM 4 — 'Thrust & Time' sekmesi.** Sıvı motorda zaman-çözümlü eğri
YOKTUR ve çözücü bunu ``throttle_map.transient_response = 'not_modelled'``
ile açıkça beyan eder. Bu doğru davranıştır; test onun kullanıcıya
GERÇEKTEN ulaştığını (uç yanıtında, JSON'a serileşmiş hâlde) kilitler.
Sıvı için zaman çözücüsü YAZILMADI — bu bilinçli bir kapsam kararıdır.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hrma.engines.liquid_rocket_engine import (          # noqa: E402
    CHAMBER_MATERIAL_DEFAULT,
    CHAMBER_MATERIAL_SOURCE_DEFAULT,
    CHAMBER_MATERIAL_SOURCE_REJECTED,
    CHAMBER_MATERIAL_SOURCE_USER,
    LIQUID_UNREAD_INPUT_FIELDS,
    SAFETY_FACTOR_DEFAULT,
    SAFETY_FACTOR_SOURCE_DEFAULT,
    SAFETY_FACTOR_SOURCE_REJECTED,
    SAFETY_FACTOR_SOURCE_USER,
    LiquidRocketEngine,
)

#: Motorun kurucu argümanlarının ortak tabanı. Testler yalnız incelenen
#: kalemi değiştirir, gerisi sabit kalır — böylece bir alanın oynattığı şey
#: başka bir alanın etkisiyle karışmaz.
TABAN = dict(thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
             fuel_type='rp1', oxidizer_type='lox',
             cooling_type='regenerative', injector_type='impinging')


def _cift(overrides=None, **kwargs):
    """(motor, sonuç) — bazı ölçümler motorun kendi zincirini de sorgular."""
    kw = dict(TABAN)
    kw.update(kwargs)
    engine = LiquidRocketEngine(overrides=dict(overrides or {}), **kw)
    return engine, engine.calculate_performance()


def _kos(overrides=None, **kwargs):
    """Motoru kurar ve tam performans çözümünü döndürür."""
    return _cift(overrides, **kwargs)[1]


# Çözüm pahalıdır (~3 s); her senaryo bir kez koşulur ve paylaşılır.
@pytest.fixture(scope='module')
def taban_cift():
    return _cift()


@pytest.fixture(scope='module')
def taban(taban_cift):
    return taban_cift[1]


@pytest.fixture(scope='module')
def basincli():
    """Basınç beslemeli çevrim — pompa/türbin YOKTUR."""
    return _kos(overrides={'engine_cycle': 'pressure_fed'})


@pytest.fixture(scope='module')
def ablatif():
    return _kos(cooling_type='ablative')


@pytest.fixture(scope='module')
def radyatif():
    return _kos(cooling_type='radiative')


@pytest.fixture(scope='module')
def tablosuz_yakit():
    """Buhar basıncı tablosunda BULUNMAYAN yakıt (metan)."""
    return _kos(fuel_type='methane')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _sayi_var_mi(nesne):
    """Sözlük/liste ağacında herhangi bir sayı (bool hariç) var mı?

    "Beyan var ama sayı yok" iddiasını ölçmek için: bir NOT_MODELLED bloğu
    metin taşıyabilir, SAYI taşıyamaz — sayı taşıyorsa o sayı uydurmadır.
    """
    if isinstance(nesne, bool):
        return False
    if isinstance(nesne, (int, float)):
        return True
    if isinstance(nesne, dict):
        return any(_sayi_var_mi(v) for v in nesne.values())
    if isinstance(nesne, (list, tuple)):
        return any(_sayi_var_mi(v) for v in nesne)
    return False


# ---------------------------------------------------------------------------
# KALEM 1a — besleme akışkanı kaydı (_feed_fluid_record)
# ---------------------------------------------------------------------------
class TestBeslemeAkiskaniKaydi:
    """Buhar basıncı HRMA'da çözülmez; tablodan gelir ya da hiç gelmez."""

    def test_tablodaki_itici_icin_kaynak_kunyeli_kayit_doner(self):
        engine = LiquidRocketEngine(**TABAN)
        for itici in ('lox', 'rp1'):
            anahtar, kayit = engine._feed_fluid_record(itici)
            assert anahtar == itici
            assert kayit is not None
            assert kayit.get('vapor_pressure_Pa') > 0, (
                f"{itici} için buhar basıncı yok; NPSH zinciri kurulamaz")
            assert kayit.get('vapor_pressure_source'), (
                'Buhar basıncı kaynak künyesi olmadan yayımlanamaz')

    def test_tablosuz_itici_icin_kayit_uydurulmaz(self):
        engine = LiquidRocketEngine(**TABAN)
        anahtar, kayit = engine._feed_fluid_record('methane')
        assert (anahtar, kayit) == (None, None), (
            'Tabloda olmayan itici için kayıt üretilmemeli')

    def test_su_kocu_ile_tek_kaynak(self):
        """İki modül iki farklı buhar basıncı varsayamaz."""
        from hrma.analysis.water_hammer import FLUID_PROPERTIES
        engine = LiquidRocketEngine(**TABAN)
        for itici in ('lox', 'rp1'):
            _, kayit = engine._feed_fluid_record(itici)
            assert kayit is FLUID_PROPERTIES[itici], (
                'Besleme kaydı su koçu tablosunun TA KENDİSİ olmalı')


# ---------------------------------------------------------------------------
# KALEM 1b — C1 turbopompa boyutlandırma bağlaması
# ---------------------------------------------------------------------------
class TestTurbopompaBoyutlandirmaBaglamasi:

    def test_turbopompali_cevrimde_zincir_gercekten_kosuyor(self, taban):
        """B5 (v2.6.27) GÜNCELLEMESİ — eski sözleşme yeni sözleşmeye çevrildi.

        Eski hâli yalnız ``'margin_m' in pompa['npsh']`` diyordu: marjın
        VARLIĞINI kilitliyordu, İŞARETİNİ değil. Ölçülen kusur (B5 teşhisi,
        2026-08-14): motor devri şişkin NPSH'tan seçilip modüle dayatılınca
        yakıt pompası marjı -14,4 m çıkıyordu ve bu test yine YEŞİLDİ —
        kusuru koruyan bekçi. Yeni sözleşmede devir derate'li emme
        sınırından gelir; tasarım noktasında marj POZİTİFTİR ve modül
        'supplied shaft speed exceeds the suction-limited maximum' uyarısı
        ÜRETMEZ. İkisi de artık kilitlidir.
        """
        blok = taban['detailed_feed_system']['turbopump_sizing']
        assert blok['status'] == 'modelled'
        for ad in ('oxidizer_pump', 'fuel_pump'):
            pompa = blok[ad]
            assert pompa['status'] == 'modelled', f'{ad} boyutlandırılmadı'
            # NPSH zinciri gerçekten çözülmüş olmalı (marj dahil).
            assert pompa['npsh']['available_m'] > 0
            assert pompa['npsh']['required_m'] > 0
            assert pompa['npsh']['margin_m'] > 0, (
                f'{ad}: tasarım noktasında NPSH marjı pozitif olmalı — '
                'negatif marj, motorun modüle yanlış devir dayattığı eski '
                'kusurun izidir')
            assert not any('suction-limited maximum' in u
                           for u in pompa.get('warnings', [])), (
                f'{ad}: motor devri emme sınırını aşıyorsa tek-kaynak '
                'zinciri bozulmuş demektir (B5 öncesi yakıt pompası vakası)')
            assert pompa['pump']['specific_speed_overall_us'] > 0
            assert pompa['pump']['stage_count'] >= 1
            assert pompa['vapor_pressure_source'], (
                'Buhar basıncı kaynak künyesiz kullanılamaz')
        assert blok['turbine']['status'] == 'modelled'
        assert blok['turbine']['mean_diameter_m'] > 0
        assert blok['turbine']['stage_count'] >= 1

    def test_iki_cark_capi_da_yayimlanir_biri_digerinin_yerine_gecmez(
            self, taban):
        """İki farklı model, iki farklı alan adı, sessiz ikame yok."""
        pompa = taban['detailed_feed_system']['turbopump_sizing'][
            'oxidizer_pump']
        d_modul = pompa['impeller_diameter_head_coefficient_m']
        d_motor = pompa['impeller_diameter_euler_stodola_m']
        assert d_modul > 0 and d_motor > 0
        assert pompa['impeller_diameter_ratio'] == pytest.approx(
            d_modul / d_motor)
        assert 'TWO INDEPENDENT ESTIMATES' in pompa['impeller_diameter_note']

    def test_mil_devri_modulce_yeniden_secilmez(self, taban):
        """Aynı yanıtta iki farklı mil devri bulunamaz.

        B5 (v2.6.27) GÜNCELLEMESİ: devir hâlâ motordan GEÇİRİLİR (mode
        'user_specified'), ama artık motorun kendisi de o devri modülün
        disipliniyle seçer (derate x emme sınırı, gerçek buhar basıncı,
        yalnız emme kaybı). Kaynak beyanı bunu söylemek zorundadır —
        eski metin 'speed set by the suction specific speed' diyordu ve
        derate'siz tam-sınır seçimini (totolojik marj) tarif ediyordu.
        """
        besleme = taban['detailed_feed_system']
        boyut = besleme['turbopump_sizing']['oxidizer_pump']
        motor_devri = besleme['turbopump_analysis']['oxidizer_pump'][
            'rotational_speed']
        assert boyut['shaft_speed']['selected_rpm'] == pytest.approx(
            motor_devri)
        assert boyut['shaft_speed']['mode'] == 'user_specified', (
            'Devir modüle seçtirilmemeli; motorun zincirinden geçirilmeli')
        assert 'engine pump design chain' in boyut['shaft_speed_source']
        assert 'SPEED_DERATE_DEFAULT' in boyut['shaft_speed_source'], (
            'Kaynak beyanı derate disiplinini söylemeli (B5)')

    def test_basinc_beslemelide_beyan_var_sayi_yok(self, basincli):
        """Pompa yoksa pompa boyutu da olmaz — gerekçesiyle."""
        blok = basincli['detailed_feed_system']['turbopump_sizing']
        assert blok['status'] == 'NOT_APPLICABLE'
        assert 'pressure-fed' in blok['reason']
        assert 'oxidizer_pump' not in blok and 'turbine' not in blok, (
            'Basınç beslemeli motorda pompa/türbin boyutu yayımlanamaz')
        assert not _sayi_var_mi({k: v for k, v in blok.items()
                                 if k != 'status'}), (
            'NOT_APPLICABLE bloğu sayı taşıyamaz')

    def test_buhar_basincsiz_itici_icin_npsh_uydurulmaz(self, tablosuz_yakit):
        """Metan tabloda yok: yakıt pompası beyanla susar, oksitleyici çalışır."""
        blok = tablosuz_yakit['detailed_feed_system']['turbopump_sizing']
        yakit = blok['fuel_pump']
        assert yakit['status'] == 'NOT_MODELLED'
        assert 'vapor_pressure' in yakit['required_inputs']
        assert 'methane' in yakit['basis']
        assert set(yakit) == {'status', 'required_inputs', 'basis'}, (
            'NOT_MODELLED pompa bloğu yalnız gerekçe taşır')
        assert not _sayi_var_mi(yakit), 'Eksik girdiyle sayı üretilmiş'
        # Eksik olan yalnız YAKIT tarafıdır; oksitleyici zinciri susmaz.
        assert blok['oxidizer_pump']['status'] == 'modelled'


# ---------------------------------------------------------------------------
# KALEM 1c — C2 vana / besleme hattı bağlaması
# ---------------------------------------------------------------------------
class TestVanaBeslemeHattiBaglamasi:

    def test_hat_butcesi_ve_vana_boyutu_gercekten_uretilir(self, taban):
        blok = taban['detailed_feed_system']['valve_feedline']
        assert blok['status'] == 'modelled'
        for ad in ('oxidizer_line', 'fuel_line'):
            hat = blok[ad]
            assert hat['status'] == 'modelled'
            assert hat['budget']['line_dp_Pa'] > 0
            assert hat['budget']['total_dp_Pa'] >= hat['budget']['line_dp_Pa']
            assert hat['valve']['capacity']['cv_required'] > 0
            assert hat['valve']['capacity']['kv_required'] > 0

    def test_hat_verisi_motorun_kendi_zincirinden_gelir(self, taban_cift):
        """C2 ikinci bir hat modeli kurmaz; aynı çapı ve aynı kayıpları alır."""
        motor, sonuc = taban_cift
        hat = sonuc['detailed_feed_system']['valve_feedline']['oxidizer_line']
        kayiplar = motor._calculate_feed_system_pressure_drops()
        cap_mm = kayiplar['oxidizer_line']['line_diameter_mm']
        # Etiket, modülün hidrolik alt sözlüğünü ezmemeli (bkz. line_label).
        assert hat['line_label'] == 'oxidizer_line'
        assert hat['line']['inputs']['line_id_m'] == pytest.approx(
            cap_mm / 1000.0)
        assert hat['line']['flow']['velocity_m_s'] > 0
        assert hat['line']['flow']['reynolds'] > 0
        assert hat['valve']['inputs']['pressure_drop_Pa'] == pytest.approx(
            kayiplar['oxidizer_line']['main_valve'] * 1e5)
        assert hat['extra_loss_coefficient'] > 0
        assert 'main valve is NOT in this sum' in hat['extra_loss_basis']

    def test_viskozite_kaynagi_beyanli(self, taban):
        hat = taban['detailed_feed_system']['valve_feedline']['oxidizer_line']
        assert 'not supplied' in hat['viscosity_source']
        kullanici = _kos(overrides={'oxidizer_viscosity': 3.0e-4})
        hat2 = kullanici['detailed_feed_system']['valve_feedline'][
            'oxidizer_line']
        assert hat2['viscosity_Pa_s'] == pytest.approx(3.0e-4)
        assert 'user input' in hat2['viscosity_source']

    def test_kritik_basincsiz_itici_icin_kavitasyon_hukmu_verilmez(
            self, tablosuz_yakit):
        """Buhar basıncı yoksa 'güvenli' denmez; tarama yapılmadığı söylenir."""
        hat = tablosuz_yakit['detailed_feed_system']['valve_feedline'][
            'fuel_line']
        assert hat['vapor_pressure_Pa'] is None
        assert hat['vapor_pressure_source'] is None
        assert 'no cavitation screening' in hat['cavitation_screening_source']

    def test_su_kocu_baglantisi_cidarsiz_koşuda_uydurulmaz(self, taban):
        """Cidar kalınlığı yoksa elastik dalga hızı tanımsızdır, öyle denir."""
        hat = taban['detailed_feed_system']['valve_feedline']['oxidizer_line']
        assert 'not produced' in hat['water_hammer_coupling_source']


# ---------------------------------------------------------------------------
# KALEM 1d — A5 pasif ısıl koruma bağlaması
# ---------------------------------------------------------------------------
class TestPasifIsilKorumaBaglamasi:

    def test_ablatifte_astar_durustce_boyutlanir_veya_reddedilir(self, ablatif):
        """B6 sözleşmesi (14 Ağu 2026): astar YÜZEY ENERJİ DENGESİYLE sürülür
        ve geçerlilik kapısından geçemeyen sayı YAYIMLANMAZ.

        Eski bekçi burada 'thickness > 0' diyordu ve 278,8 mm'lik fizikdışı
        astarı KORUYORDU (NASA TM-107041'e karşı ~109x fazla tahmin; boğaz
        astarı boğaz yarıçapının 184 katı). Yeni sözleşme: soğuk-cidar Bartz
        akısı doğrudan Q* modeline verilmez (flux_basis bunu beyan eder);
        gereken kalınlık istasyon yarıçapını aşarsa hüküm 'sized' değil
        NOT_MODELLED'dır ve kalınlık alanı basılmaz.
        """
        blok = ablatif['thermal_protection']['passive_thermal_protection']
        assert blok['status'] == 'modelled'
        for istasyon in ('chamber_liner', 'nozzle_entry_liner'):
            astar = blok[istasyon]
            # Yeni yol: akı, yüzey enerji dengesinden (üfleme + ışıma düşülür).
            assert astar['flux_basis'] == 'surface_energy_balance'
            assert astar['h_gas_W_m2K'] > 0
            assert astar['T_surface_K'] > 0
            assert astar['burn_time_s'] == pytest.approx(blok['burn_time_s'])
            # Bu senaryo (100 bar + 300 s) ablatifin zarfının DIŞINDADIR —
            # ölçüldü: kamara astarı 73,7 mm > yarıçap 49,6 mm. Dürüst hüküm:
            assert astar['thickness_status'] == 'NOT_MODELLED'
            assert astar['model_valid'] is False
            assert 'OUT OF ENVELOPE' in astar['basis']
            # Sayı yayımlanmaz — uydurma kalınlık ekrana çıkamaz.
            assert astar.get('thickness') in (None, 0) or \
                'thickness' not in astar
        assert blok['wall_temperature_history']['status'] == 'modelled'

    def test_astar_akisi_cozucunun_kendi_akisidir(self, ablatif):
        """Boğaz astarı boğaz akısıyla, hazne astarı hazne akısıyla."""
        isil = ablatif['thermal_protection']
        blok = isil['passive_thermal_protection']
        # thermal_protection MW/m2, astar kW/m2 taşır (bkz. _liner).
        assert blok['chamber_liner']['heat_flux_kw_m2'] == pytest.approx(
            isil['chamber_heat_flux'] * 1000.0, rel=1e-6)
        assert blok['nozzle_entry_liner']['heat_flux_kw_m2'] == pytest.approx(
            isil['heat_flux'] * 1000.0, rel=1e-6)

    def test_radyatifte_isinim_dengesi_var_astar_yok(self, radyatif):
        blok = radyatif['thermal_protection']['passive_thermal_protection']
        assert blok['status'] == 'modelled'
        assert blok['radiation_equilibrium']['status'] == 'modelled'
        assert blok['radiation_equilibrium']['T_wall_eq_K'] > 0
        # Modül kendi muhafazakârlık uyarısını taşımalı (görüş faktörü 1,
        # gaz ışınımı sıfır): "güvenli" hükmü sessizce verilmez.
        assert 'unconservative' in blok['radiation_equilibrium']
        assert 'chamber_liner' not in blok, (
            'Işınımla soğutulan cidara ablatif astar boyutlandırılamaz')

    def test_aktif_sogutmada_ikinci_isil_koruma_iddiasi_uretilmez(self, taban):
        blok = taban['thermal_protection']['passive_thermal_protection']
        assert blok['status'] == 'NOT_APPLICABLE'
        assert 'actively cooled' in blok['reason']
        assert not _sayi_var_mi({k: v for k, v in blok.items()
                                 if k != 'status'})

    def test_blok_kendi_adresinde_yayimlanir_koku_kirletmez(
            self, taban, ablatif, radyatif):
        """Düzeltilen kusur: 'modelled' dal sonucu köke serpiyordu.

        Üç dal da AYNI adreste durmalı; ısıl koruma bloğunun kökündeki
        ``cooling_type`` ezilmemeli ve astara ait ``status`` köke çıkmamalı.
        """
        for sonuc, beklenen in ((taban, 'Regenerative'),
                                (ablatif, 'Ablative'),
                                (radyatif, 'Radiative')):
            isil = sonuc['thermal_protection']
            assert 'passive_thermal_protection' in isil
            assert isil['cooling_type'] == beklenen, (
                'Pasif blok ısıl koruma bloğunun cooling_type alanını eziyor')
            assert 'status' not in isil, (
                'Astar boyutlandırmasının hükmü ısıl koruma bloğunun '
                'tamamına aitmiş gibi köke çıkmamalı')
            assert 'chamber_liner' not in isil

    def test_astar_hukmu_uc_yanitina_kadar_gelir(self, client):
        """Bağlama motorda kalmamalı: kullanıcı HÜKMÜ yanıtta görmeli.

        B6 sözleşmesi: bu senaryoda dürüst hüküm bir sayı değil, gerekçeli
        bir NOT_MODELLED'dır (bkz. üstteki bekçinin açıklaması) — ve o hüküm
        gerekçesiyle birlikte HTTP yanıtına kadar taşınmalıdır.
        """
        yanit = client.post('/calculate_liquid', json={
            'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5,
            'fuel_type': 'rp1', 'oxidizer_type': 'lox',
            'cooling_type': 'ablative',
        })
        assert yanit.status_code == 200
        blok = yanit.get_json()['thermal_protection'][
            'passive_thermal_protection']
        assert blok['status'] == 'modelled'
        astar = blok['chamber_liner']
        assert astar['thickness_status'] == 'NOT_MODELLED'
        assert astar['flux_basis'] == 'surface_energy_balance'
        assert 'OUT OF ENVELOPE' in astar['basis']


# ---------------------------------------------------------------------------
# KALEM 2 — emniyet katsayısı ve malzeme KAYNAK beyanı
# ---------------------------------------------------------------------------
class TestYapisalKaynakBeyani:

    def test_varsayilan_kullanildiginda_varsayilan_denir(self, taban):
        hazne = taban['structural_analysis']['chamber_structure']
        assert hazne['safety_factor'] == pytest.approx(SAFETY_FACTOR_DEFAULT)
        assert hazne['safety_factor_source'] == SAFETY_FACTOR_SOURCE_DEFAULT
        assert hazne['material_key'] == CHAMBER_MATERIAL_DEFAULT
        assert (hazne['material_selection_source']
                == CHAMBER_MATERIAL_SOURCE_DEFAULT)

    def test_kullanici_girdisi_kullanici_diye_beyan_edilir(self):
        sonuc = _kos(overrides={'safety_factor': 1.6,
                                'chamber_material': 'steel_304'})
        hazne = sonuc['structural_analysis']['chamber_structure']
        assert hazne['safety_factor'] == pytest.approx(1.6)
        assert hazne['safety_factor_source'] == SAFETY_FACTOR_SOURCE_USER
        assert hazne['material_key'] == 'ss_304'
        assert (hazne['material_selection_source']
                == CHAMBER_MATERIAL_SOURCE_USER)

    def test_reddedilen_girdiye_sahip_cikilmaz(self):
        """Aralık dışı katsayı / tanınmayan malzeme: künye doğruyu söyler."""
        sonuc = _kos(overrides={'safety_factor': 99,
                                'chamber_material': 'titanyum'})
        hazne = sonuc['structural_analysis']['chamber_structure']
        assert hazne['safety_factor'] == pytest.approx(SAFETY_FACTOR_DEFAULT)
        assert hazne['safety_factor_source'] == SAFETY_FACTOR_SOURCE_REJECTED
        assert hazne['material_key'] == CHAMBER_MATERIAL_DEFAULT
        assert (hazne['material_selection_source']
                == CHAMBER_MATERIAL_SOURCE_REJECTED)
        kodlar = {u['code'] for u in sonuc['input_warnings']}
        assert 'warn.liquid.input_out_of_range' in kodlar
        assert 'warn.liquid.option_not_recognised' in kodlar

    def test_malzeme_secimi_ile_veritabani_kunyesi_ayri_sorulardir(self, taban):
        hazne = taban['structural_analysis']['chamber_structure']
        assert hazne['material_source'] != hazne['material_selection_source']
        # material_source malzeme ÖZELLİKLERİNİN literatür künyesidir.
        assert 'Special Metals' in hazne['material_source']

    def test_tank_ve_hazne_ayni_kunyeyi_kullanir(self):
        """İki blok aynı durumu iki farklı cümleyle anlatamaz."""
        for overrides, beklenen in (
                ({}, SAFETY_FACTOR_SOURCE_DEFAULT),
                ({'safety_factor': 1.6}, SAFETY_FACTOR_SOURCE_USER),
                ({'safety_factor': 99}, SAFETY_FACTOR_SOURCE_REJECTED)):
            sonuc = _kos(overrides=overrides)
            hazne = sonuc['structural_analysis']['chamber_structure']
            tank = sonuc['propellant_tanks']['oxidizer_tank']['structural']
            assert hazne['safety_factor_source'] == beklenen
            assert tank['safety_factor_source'] == beklenen

    def test_katsayi_yalniz_etikete_degil_kalinliga_da_gider(self):
        """Beyan doğru olsun diye sayının gerçekten kullanıldığı da ölçülür."""
        yumusak = _kos(overrides={'safety_factor': 1.2})
        sert = _kos(overrides={'safety_factor': 5.0})
        a = yumusak['structural_analysis']['chamber_structure']
        b = sert['structural_analysis']['chamber_structure']
        assert b['required_wall_thickness'] > a['required_wall_thickness']
        assert b['allowable_stress'] < a['allowable_stress']


# ---------------------------------------------------------------------------
# KALEM 3 — okunmayan gövde alanı sessizce yutulmaz
# ---------------------------------------------------------------------------
class TestOkunmayanGirdiBeyani:

    def test_genisleme_orani_takma_adi_beyan_edilir(self):
        sonuc = _kos(overrides={'expansion_ratio': 60})
        beyanlar = {b['field']: b for b in sonuc.get('inputs_not_used') or []}
        assert 'expansion_ratio' in beyanlar, (
            'Kullanıcının genişleme oranı sessizce yok sayıldı; beyan yok')
        beyan = beyanlar['expansion_ratio']
        assert beyan['submitted'] == pytest.approx(60.0)
        assert beyan['used_by_model'] == pytest.approx(
            sonuc['expansion_ratio'])
        assert beyan['reason'] == 'field_not_read'
        # "Kullanılmadı" demek, doğrusunu söylemeden yarım kalır.
        assert beyan['use_instead'] == 'nozzle_expansion_ratio'
        assert 'nozzle_expansion_ratio' in beyan['message']

    def test_beyan_kullaniciya_uyari_olarak_da_ulasir(self):
        sonuc = _kos(overrides={'expansion_ratio': 60})
        uyari = [u for u in sonuc['input_warnings']
                 if u['code'] == 'warn.liquid.input_field_not_read']
        assert uyari, ('Beyan yalnız derin bir alanda kalmamalı; uyarı '
                       'listesine de düşmeli')
        assert uyari[0]['params']['use_instead'] == 'nozzle_expansion_ratio'

    def test_dogru_alan_adi_gercekten_calisir(self):
        """Beyanın anlamlı olması için doğrusunun çalışıyor olması gerekir."""
        sonuc = _kos(overrides={'nozzle_expansion_ratio': 60})
        assert sonuc['expansion_ratio'] == pytest.approx(60.0)
        assert 'inputs_not_used' not in sonuc, (
            'Gerçekten kullanılan girdi "kullanılmadı" diye beyan edilemez'
        )
        assert (sonuc['nozzle_angles']['expansion_ratio_source']
                == 'user input (nozzle expansion ratio)')

    def test_cakisma_yokken_beyan_uretilmez(self, taban):
        """Beyan VARSAYIMLA değil ÖLÇÜMLE üretilir."""
        assert 'inputs_not_used' not in taban
        cozulen = taban['expansion_ratio']
        sonuc = _kos(overrides={'expansion_ratio': cozulen})
        assert 'inputs_not_used' not in sonuc, (
            'Gönderilen değer kullanılan değere eşitken yanlış alarm verildi')

    def test_takma_ad_gizlice_girdiye_baglanmaz(self):
        """`expansion_ratio` aynı yanıtın ÇIKTI adıdır; girdi olamaz.

        Bağlansaydı, sonucu geri gönderen her istemci (proje kaydı, dışa
        aktarım turu) lüleyi farkında olmadan sabitlerdi.
        """
        assert 'expansion_ratio' in LIQUID_UNREAD_INPUT_FIELDS
        for eps in (4, 20, 60, 150, 400):
            sonuc = _kos(overrides={'expansion_ratio': eps})
            assert sonuc['expansion_ratio'] != pytest.approx(float(eps))
            assert (sonuc['nozzle_angles']['expansion_ratio_source']
                    == 'ambient-matched at sea level')

    def test_uc_yanitinda_da_beyan_var(self, client):
        yanit = client.post('/calculate_liquid', json={
            'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5,
            'fuel_type': 'rp1', 'oxidizer_type': 'lox',
            'expansion_ratio': 60,
        })
        assert yanit.status_code == 200
        gövde = yanit.get_json()
        alanlar = {b['field'] for b in gövde.get('inputs_not_used') or []}
        assert 'expansion_ratio' in alanlar, (
            'Beyan motorda üretiliyor ama uç yanıtına ulaşmıyor')


# ---------------------------------------------------------------------------
# KALEM 4 — geçici rejim beyanının kullanıcıya ulaşması
# ---------------------------------------------------------------------------
class TestGeciciRejimBeyani:
    """Sıvı motorda zaman-çözümlü eğri YOK; beyan bunu söylüyor mu?

    Sekmenin adı A6'da içeriğiyle hizalandı (şablon işi). Buradaki bekçi
    ÇÖZÜCÜ tarafını tutar: beyan üretiliyor, uca kadar geliyor ve kısma
    haritası "kararlı hâl" olduğunu ayrıca yazıyor.
    """

    def test_cozucu_gecici_rejimi_modellemedigini_soyler(self, taban):
        harita = taban['throttle_map']
        assert harita['transient_response'] == 'not_modelled'
        # Kararlı hâl kaydı ayrıca yazılı olmalı. Metin dili bu bekçinin
        # konusu değildir (bkz. kalan risk: bu liste hâlâ backend'de Türkçe
        # sabit taşıyor), bu yüzden iki dilin de anahtar sözcüğü kabul edilir.
        anahtarlar = ('Geçici rejim', 'transient', 'KARARLI', 'steady')
        assert any(any(k in v for k in anahtarlar)
                   for v in harita['assumptions']), (
            'Her noktanın KARARLI hâl çözümü olduğu ayrıca söylenmeli')

    def test_beyan_uc_yanitina_kadar_gelir(self, client):
        yanit = client.post('/calculate_liquid', json={
            'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5,
            'fuel_type': 'rp1', 'oxidizer_type': 'lox',
        })
        assert yanit.status_code == 200
        gövde = yanit.get_json()
        assert gövde['throttle_map']['transient_response'] == 'not_modelled'

    def test_zaman_cozumlu_egri_uydurulmaz(self, taban):
        """Beyan varken bir de sahte zaman serisi yayımlanmamalı."""
        harita = taban['throttle_map']
        yasak = {'time_s', 'thrust_curve', 'time_history', 'transient_curve'}
        assert not (yasak & set(harita)), (
            'Modellenmediği beyan edilen geçici rejim için eğri yayımlanmış')
        for nokta in harita['points']:
            assert 'time_s' not in nokta

    def test_gecici_rejim_alanlari_beyanli_bagsiz(self, taban):
        """Başlangıç/kapama süreleri hâlâ 'modellenmedi' kulvarında olmalı."""
        beyan = taban['unwired_inputs']['transient_not_modelled']
        for alan in ('engine_start_time', 'engine_shutdown_time',
                     'throttle_response'):
            assert alan in beyan
