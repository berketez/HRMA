"""ÖH Dalga-15 · kulvar **app-api** · aşama 3 — onarım bekçileri.

Her sınıf bir defter kalemine bağlıdır ve iddiası ÖLÇÜLMÜŞ vakalardan
kurulur (``docs/scofield/raw/OH/D15/app-api/a3/once.json`` ⟷ ``sonra.json``).
Sayılar üründen İTHAL EDİLMEZ; koşum çıktısından gelir.

Ters-mutasyon tablosu: ``docs/scofield/raw/OH/D15/app-api/a3/mutasyon.py``
(her onarım geçici olarak geri alınır, ilgili sınıf KIRMIZI olmalı).
"""

import contextlib
import io
import warnings

import pytest

warnings.filterwarnings('ignore')

G0 = 9.80665


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _post(client, yol, govde):
    return _sessiz(client.post, yol, json=govde)


#: Yörünge ucunun ARAÇ tarafı — dördü de gerçek bir koşum için gerekli.
ARAC = {'initial_mass': 50, 'final_mass': 25,
        'drag_coefficient': 0.5, 'reference_area': 0.1}
MOTOR = {'thrust': 5000, 'burn_time': 8}
#: Kütle bütçesiyle TUTARLI isp: m_p/t_b = 25/8 = 3,125 kg/s.
ISP_TUTARLI = MOTOR['thrust'] / ((50 - 25) / MOTOR['burn_time'] * G0)


# ===========================================================================
# P7B3-17 — /api/trajectory-analysis uydurma ARAÇ
# ===========================================================================
class TestP7B317UydurmaArac:
    """Araç verilmeden yörünge yayımlanamaz.

    ÖLÇÜLDÜ (``once.json``): ``{thrust: 5000, burn_time: 8}`` gövdesi
    HTTP 200 ve 876 noktalı tam bir yörünge alıyordu; apoje 3.311,33 m.
    O rakam 50/25 kg, Cd 0,5, 0,1 m² kesitli bir ROKETE aitti ve dört
    sayının hiçbirini kullanıcı vermemişti. ``vehicle_beyan_alanlari``
    ölçümde BOŞTU — tek bir uyarı bile yoktu.
    """

    def test_arac_verilmeyince_yorunge_yayimlanmaz(self, client):
        r = _post(client, '/api/trajectory-analysis', dict(MOTOR))
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        j = r.get_json()
        assert j['error'] == 'missing_vehicle_parameters'
        # Kullanıcı NEYİ göndereceğini öğrenmeli: dördü de adıyla anılır.
        assert set(j['missing_fields']) == set(ARAC)

    def test_eksik_tek_alan_da_adiyla_reddedilir(self, client):
        for eksik in ARAC:
            govde = dict(MOTOR, **{k: v for k, v in ARAC.items()
                                   if k != eksik})
            r = _post(client, '/api/trajectory-analysis', govde)
            assert r.status_code == 422, eksik
            assert r.get_json()['missing_fields'] == [eksik]

    def test_arac_verilince_gecerli_yol_korunur(self, client):
        """Onarım, gerçekten çalışan koşumu bozmamalı."""
        r = _post(client, '/api/trajectory-analysis', dict(MOTOR, **ARAC))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        td = r.get_json()['trajectory_data']
        apoje = td['performance']['trajectory_metrics']['max_altitude']
        assert apoje > 0
        # Araç, İSTEKTE ne verildiyse odur (uydurma yok).
        vp = td['vehicle_parameters']
        assert vp['mass_dry'] == ARAC['final_mass']
        assert vp['drag_coefficient'] == ARAC['drag_coefficient']

    def test_gonderilmis_ama_okunamayan_alan_kendi_adiyla_reddedilir(
            self, client):
        """Eksik-araç hükmü, okunamayan alanı GÖLGELEMEMELİ.

        ``total_impulse: 'cok'`` gövdesi eskiden "araç eksik" diyordu;
        kullanıcı yanlış alanı düzeltmeye çalışırdı.
        """
        r = _post(client, '/api/trajectory-analysis',
                  dict(MOTOR, total_impulse='cok'))
        assert r.status_code == 422
        assert 'total_impulse' in r.get_data(as_text=True)


# ===========================================================================
# P7B3-18 — isp ÖLÜ GİRDİ KANALI
# ===========================================================================
class TestP7B318IspOluKanal:
    """isp ya yörüngeyi etkiler ya da çelişkiyi durdurur.

    ÖLÇÜLDÜ (``probe2``, taban ``e88d096``): isp 0 / 100 / 200 / 300 / 450
    için apoje TEK BASAMAĞA KADAR aynıydı (3.311,3294236230495 m, 876
    nokta). Çözücü ``mass_flow_rate``ı hiç okumuyor; yanıt ise
    ``F/(Isp·g0)`` ile hesaplanmış BAŞKA bir debiyi yayımlıyordu.
    """

    def test_celiskili_isp_sessizce_cozulmez(self, client):
        # 5000 N · 8 s / (450 · 9,80665) = 9,06 kg ⟷ bütçe 25 kg (2,8 kat).
        r = _post(client, '/api/trajectory-analysis',
                  dict(MOTOR, **ARAC, isp=450))
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        j = r.get_json()
        assert j['error'] == 'inconsistent_propellant_budget'
        # İKİ sayı da geri verilir; kullanıcı hangisini düzelteceğini bilsin.
        alanlar = {f['field'] for f in j['invalid_fields']}
        assert {'isp', 'initial_mass', 'final_mass'} <= alanlar
        assert j['propellant_mass_from_mass_budget_kg'] == pytest.approx(25.0)

    def test_tutarli_isp_kabul_edilir(self, client):
        r = _post(client, '/api/trajectory-analysis',
                  dict(MOTOR, **ARAC, isp=ISP_TUTARLI))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]

    def test_yayimlanan_debi_cozucunun_kullandigi_debidir(self, client):
        """Tek yanıtta iki farklı kütle debisi olamaz."""
        r = _post(client, '/api/trajectory-analysis', dict(MOTOR, **ARAC))
        md = r.get_json()['trajectory_data']['motor_data']
        beklenen = md['propellant_mass_total'] / md['burn_time']
        assert md['mass_flow_rate'] == pytest.approx(beklenen, rel=1e-12)
        assert 'mass_flow_rate_basis' in md

    def test_isp_verilmezse_uydurulmaz_turetilir(self, client):
        """Eskiden 200 s uyduruluyordu; artık bütçeden türetilir."""
        r = _post(client, '/api/trajectory-analysis', dict(MOTOR, **ARAC))
        md = r.get_json()['trajectory_data']['motor_data']
        assert md['isp'] != 200.0
        assert md['isp'] == pytest.approx(ISP_TUTARLI, rel=1e-9)
        assert 'isp_basis' in md

    def test_isp_kanali_artik_olu_degil(self, client):
        """Kanalın CANLI olduğunun tek cümlelik kanıtı.

        Ölçümün kendisi: farklı isp'ler artık AYNI 200'ü vermiyor.
        """
        kodlar = {isp: _post(client, '/api/trajectory-analysis',
                             dict(MOTOR, **ARAC, isp=isp)).status_code
                  for isp in (100, 300, 450, ISP_TUTARLI)}
        assert len(set(kodlar.values())) > 1, kodlar

    def test_sifir_isp_reddedilir(self, client):
        r = _post(client, '/api/trajectory-analysis',
                  dict(MOTOR, **ARAC, isp=0))
        assert r.status_code == 422
        assert 'isp' in r.get_data(as_text=True)


# ===========================================================================
# P7B1-02 — /calculate sessiz 20 bar
# ===========================================================================
HIBRIT = {'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
          'of_ratio': 6.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}


class TestP7B102SessizOdaBasinci:
    """Varsayılan uygulandıysa ADIYLA yayımlanır (ÖK-19).

    ÖLÇÜLDÜ (``once.json``): ``chamber_pressure`` anahtarı hiç olmayan gövde
    ile ``chamber_pressure: 20.0`` gönderen gövde BİT-AYNI yanıt üretiyordu
    (``iki_govde_bit_ayni: true``, ``fark_yaprak_sayisi: 0``).
    """

    def test_varsayilan_beyan_edilir(self, client):
        r = _post(client, '/calculate', dict(HIBRIT))
        assert r.status_code == 200
        beyan = r.get_json().get('defaults_applied')
        assert beyan, 'varsayılan uygulandı ama beyan edilmedi'
        kayit = [b for b in beyan if b['field'] == 'chamber_pressure']
        assert kayit and kayit[0]['reason'] == 'not_supplied'
        assert kayit[0]['unit'] == 'bar'

    def test_deger_gonderilince_beyan_yok_ve_govde_bit_ayni(self, client):
        """Sağlıklı yol BOZULMAZ — çapa bu iddiaya dayanıyor.

        ÖH D26 / P16B3-02 (sivi a1) — İDDİA DARALTILDI, GEVŞETİLMEDİ.
        Eski hâli ``'defaults_applied' not in a.get_json()`` diyordu; yani
        pc künyesinin yokluğunu değil, LİSTENİN TAMAMININ yokluğunu
        sınıyordu. Bu, ucun UYGULADIĞI ikinci varsayılanın
        (``cooling_channels`` -> ``'none'``, yani SOĞUTMASIZ oda)
        SESSİZ kalmasına dayanıyordu: kabul ÖK-19 gereği adıyla
        yayımlanır yayımlanmaz bu satır kırmızıya dönüyordu. Yani bekçi,
        yazarının niyeti bu olmasa da, bir kusuru KİLİTLİYORDU.

        Bekçinin gerçek iddiası şudur ve aynen korunmuştur: kullanıcı
        ``chamber_pressure`` GÖNDERDİYSE onun için künye DOĞMAZ. Yanlışlıkla
        doğarsa test yine kırmızıdır.
        """
        a = _post(client, '/calculate', dict(HIBRIT, chamber_pressure=20.0))
        assert a.status_code == 200
        beyan = a.get_json().get('defaults_applied') or []
        alanlar = [b.get('field') if isinstance(b, dict) else b
                   for b in beyan]
        assert 'chamber_pressure' not in alanlar, (
            'kullanıcı oda basıncını gönderdi, uç yine de varsayılan '
            f'beyan etti: {alanlar}')

    def test_iki_govde_artik_ayirt_edilebilir(self, client):
        yok = _post(client, '/calculate', dict(HIBRIT)).get_data(as_text=True)
        yirmi = _post(client, '/calculate',
                      dict(HIBRIT, chamber_pressure=20.0)).get_data(as_text=True)
        assert yok != yirmi, 'iki gövde hâlâ bit-aynı'


# ===========================================================================
# P7B1-04 — gamma / gas_constant ÖLÜ GİRDİ KANALI
# ===========================================================================
class TestP7B104GammaGasConstant:
    """Çözücünün kendi bulduğu büyüklük, girdi gibi yutulamaz.

    ÖLÇÜLDÜ (``once.json``): gamma 1,05/1,15/1,25/1,35/1,45 gönderen BEŞ
    gövdenin imzası tekti (``ae727d6489573d76``) ve gamma'nın hiç
    gönderilmediği gövdeyle aynıydı; ``gas_constant`` 250/300/400 için de
    tek imza. ``_CALCULATE_SOLVER_OWNED_FIELDS`` iki alanı da kapsamıyordu
    (``gamma_kapsanmis: false``, ``gas_constant_kapsanmis: false``).
    """

    def test_demet_iki_alani_da_kapsar(self):
        from hrma.app import _CALCULATE_SOLVER_OWNED_FIELDS
        assert 'gamma' in _CALCULATE_SOLVER_OWNED_FIELDS
        assert 'gas_constant' in _CALCULATE_SOLVER_OWNED_FIELDS

    def test_gonderilen_gamma_kullanilmadigi_soylenir(self, client):
        r = _post(client, '/calculate',
                  dict(HIBRIT, chamber_pressure=30.0, gamma=1.45))
        assert r.status_code == 200
        beyan = r.get_json().get('inputs_not_used') or []
        kayit = [b for b in beyan if b['field'] == 'gamma']
        assert kayit, 'gamma yutuldu — beyan yok'
        assert kayit[0]['submitted'] == pytest.approx(1.45)
        assert kayit[0]['used_by_model'] != pytest.approx(1.45)

    def test_gonderilen_gas_constant_kullanilmadigi_soylenir(self, client):
        r = _post(client, '/calculate',
                  dict(HIBRIT, chamber_pressure=30.0, gas_constant=400.0))
        assert r.status_code == 200
        beyan = r.get_json().get('inputs_not_used') or []
        kayit = [b for b in beyan if b['field'] == 'gas_constant']
        assert kayit, 'gas_constant yutuldu — beyan yok'
        assert kayit[0]['submitted'] == pytest.approx(400.0)

    def test_cozucunun_R_si_yayimlanir_ve_molekul_agirligiyla_tutarlidir(
            self, client):
        """Beyan ancak SONUÇTA duran sayı varsa ölçülebilir."""
        from hrma.constants import R_UNIVERSAL
        r = _post(client, '/calculate', dict(HIBRIT, chamber_pressure=30.0))
        motor = r.get_json()['motor']
        assert motor.get('gas_constant') is not None
        assert motor['gas_constant'] == pytest.approx(
            R_UNIVERSAL / motor['molecular_weight'], rel=1e-12)

    def test_dogru_deger_gonderilirse_beyan_yok(self, client):
        """Beyan VARSAYIMLA değil ÖLÇÜMLE üretilir."""
        r = _post(client, '/calculate', dict(HIBRIT, chamber_pressure=30.0))
        cozulen = r.get_json()['motor']['gamma']
        r2 = _post(client, '/calculate',
                   dict(HIBRIT, chamber_pressure=30.0, gamma=cozulen))
        beyan = r2.get_json().get('inputs_not_used') or []
        assert not [b for b in beyan if b['field'] == 'gamma']


# ===========================================================================
# P7B3-35 — /api/export-stl fizik dışı geometri
# ===========================================================================
STL = {'motor_type': 'hybrid', 'chamber_diameter': 0.15,
       'chamber_length': 0.4, 'port_diameter': 0.05,
       'throat_diameter': 0.03, 'exit_diameter': 0.08}


def _stl(client, **ek):
    md = dict(STL)
    md.update(ek)
    return _sessiz(client.post, '/api/export-stl', json={'motor_data': md})


class TestP7B335FizikDisiGeometri:
    """İmal edilemez katı, indirilebilir dosya olarak teslim edilemez.

    ÖLÇÜLDÜ (``once.json`` + ``probe3``): ``chamber_length=-0,5`` ve
    ``chamber_diameter=-0,15`` HAM 500 veriyordu (suçlu olarak üretici
    gösteriliyordu); ``throat_diameter=0,5`` (odadan geniş boğaz) ve
    ``port_diameter=0,90`` ise HTTP 200 + 288.084 baytlık geçerli STL.
    """

    @pytest.mark.parametrize('alan', ['chamber_length', 'chamber_diameter',
                                      'throat_diameter', 'exit_diameter'])
    def test_negatif_olcu_adiyla_reddedilir(self, client, alan):
        r = _stl(client, **{alan: -0.5})
        assert r.status_code == 422, r.get_data(as_text=True)[:200]
        j = r.get_json()
        assert j['error'] == 'invalid_export_geometry'
        assert [f['field'] for f in j['invalid_fields']] == [alan]
        assert j['invalid_fields'][0]['reason'] == 'must_be_positive'

    def test_bogaz_odadan_genis_olamaz(self, client):
        r = _stl(client, throat_diameter=0.5)
        assert r.status_code == 422
        f = r.get_json()['invalid_fields'][0]
        assert f['field'] == 'throat_diameter'
        assert f['conflicts_with'] == 'chamber_diameter'

    def test_port_odadan_genis_olamaz(self, client):
        r = _stl(client, port_diameter=0.90)
        assert r.status_code == 422
        assert r.get_json()['invalid_fields'][0]['field'] == 'port_diameter'

    def test_cikis_bogazdan_dar_olamaz(self, client):
        r = _stl(client, exit_diameter=0.01)
        assert r.status_code == 422
        assert r.get_json()['invalid_fields'][0]['field'] == 'throat_diameter'

    def test_saglikli_geometri_hala_stl_uretir(self, client):
        r = _stl(client)
        assert r.status_code == 200
        assert r.headers['Content-Type'] == 'application/sla'
        assert len(r.get_data()) > 1000


# ===========================================================================
# P7B3-34 — _reject_incomplete_stl_geometry mesajı
# ===========================================================================
class TestP7B334MesajDogruSoyluyor:
    """Zorunlu tutulan alanın çıktıdaki karşılığı DOĞRU anlatılmalı.

    ÖLÇÜLDÜ (``probe3``): ``port_diameter`` 0,02 / 0,05 / 0,12 / 0,20
    gövdelerinin STL çıktısı BAYT ÖZDEŞ (md5 ``2b74e342830e``); aynı
    süpürmede ``chamber_diameter`` / ``chamber_length`` /
    ``throat_diameter`` / ``exit_diameter`` md5'i DEĞİŞTİRİYOR. Eski
    ret mesajı yine de "These values define the exported solid" diyordu.
    """

    def test_mesaj_artik_kati_tanimliyor_demiyor(self, client):
        r = _stl(client, port_diameter=None)
        assert r.status_code == 422
        j = r.get_json()
        assert j['missing_fields'] == ['port_diameter']
        assert 'define the exported solid' not in j['error']

    def test_temsil_edilmeyen_alan_makine_okur_bicimde_soylenir(self, client):
        r = _stl(client, port_diameter=None)
        j = r.get_json()
        assert j.get('not_represented_in_mesh') == ['port_diameter']
        assert 'not_represented_in_mesh_basis' in j

    def test_olculen_gercek_hala_gecerli(self, client):
        """Envanter ÇÜRÜRSE bekçi haber verir.

        port_diameter bir gün gerçekten mesh'e girerse bu test kırmızı olur
        ve ``_STL_FIELDS_NOT_IN_MESH`` künyesinin güncellenmesi gerektiğini
        söyler — künye sessizce yalana dönüşmesin.
        """
        import hashlib
        from hrma.app import _STL_FIELDS_NOT_IN_MESH
        assert 'port_diameter' in _STL_FIELDS_NOT_IN_MESH['hybrid']
        imzalar = {hashlib.md5(_stl(client, port_diameter=p).get_data())
                   .hexdigest() for p in (0.02, 0.05, 0.12)}
        assert len(imzalar) == 1, (
            'port_diameter artık katıyı DEĞİŞTİRİYOR; '
            '_STL_FIELDS_NOT_IN_MESH güncellenmeli')

    def test_kati_tanimlayan_alanlar_gercekten_tanimliyor(self, client):
        """Mesajın DOĞRU kalan yarısı da ölçülür (iki yönlü kilit)."""
        import hashlib
        taban = hashlib.md5(_stl(client).get_data()).hexdigest()
        for alan, deger in (('chamber_diameter', 0.30),
                            ('chamber_length', 0.90),
                            ('throat_diameter', 0.06),
                            ('exit_diameter', 0.20)):
            imza = hashlib.md5(_stl(client, **{alan: deger}).get_data())\
                .hexdigest()
            assert imza != taban, f'{alan} katıyı değiştirmiyor'


# ===========================================================================
# P7B3-28 — wall-profile kapısı ve onu KİLİTLEYEN bekçi
# ===========================================================================
WP = {'chamber_pressure': 50, 'chamber_temperature': 3000,
      'chamber_diameter': 0.15, 'chamber_length': 0.4,
      'burn_time': 10, 'mdot_total': 2.0}


class TestP7B328CidarProfiliKapisi:
    """Kapı ÖLÇÜLEREK tescillenir; kilitleyen bekçi çevrildi.

    Kalemin kendi metni "bekçisi kusuru KİLİTLİYOR" diyordu: suçlu
    ``tests/test_z5s_ham_500.py::test_wall_profile_bos_govde_ile_tam_govde_ayni``
    idi ve BOŞ gövdenin TAM gövdeyle aynı 200'ü vermesini şart koşuyordu —
    yani sessiz varsayılanları sözleşme yapıyordu. Bu dalgada çevrildi.
    """

    def test_bos_govde_adiyla_reddedilir(self, client):
        r = _post(client, '/api/analysis/wall-profile', {})
        assert r.status_code == 422
        assert r.get_json()['error'] == 'incomplete_wall_profile_input'

    @pytest.mark.parametrize('alan,deger', [
        ('chamber_pressure', -5), ('chamber_temperature', -300),
        ('mdot_total', 0)])
    def test_fizik_disi_girdi_alan_adiyla_reddedilir(self, client, alan,
                                                     deger):
        r = _post(client, '/api/analysis/wall-profile',
                  dict(WP, **{alan: deger}))
        assert r.status_code == 422
        assert [f['field'] for f in r.get_json()['invalid_fields']] == [alan]

    def test_saglikli_govde_gercek_profil_verir(self, client):
        r = _post(client, '/api/analysis/wall-profile', dict(WP))
        assert r.status_code == 200
        hg = r.get_json()['wall_profile']['h_g']
        assert len(hg) == 40
        assert not [v for v in hg if v is None]


# ===========================================================================
# P7B4-04 — oksitleyici yoğunluğu (kalem ÖLÇÜMLE ÇÜRÜTÜLDÜ)
# ===========================================================================
class TestP7B404OksitleyiciYogunlugu:
    """Kalemin İDDİA ETTİĞİ sayılar tabanda ARTIK YOK — ölçüm tescili.

    Kalem "293 K'de LOX 329", "N2O +%27,5", "tanınmayan oksitleyici
    sessizce LOX" diyordu. ÖLÇÜLDÜ (``once.json``, taban ``e88d096``):
    LOX@293,15 = 1141,0 (329 DEĞİL), N2O@293,15 = 785,10 (literatür
    değeri), tanınmayan ad ``OxidizerStateError`` yükseltiyor. Kalem
    Z1 dalgasında kapanmış.

    Bu sınıf, kapanışın GERİ GELMEMESİ için ölçümü çiviler ve tabanda
    DURAN asimetriyi de görünür kılar: N2O'nun bandı var, LOX/N2O4/H2O2
    aynı bandı görmüyor (sahibi ``hrma/data/external_data_fetcher.py``,
    bu kulvarın sahası DEĞİL — kayıt niyetiyle konuldu).
    """

    def test_taninmayan_oksitleyici_sessizce_lox_olmaz(self):
        from hrma.app import get_oxidizer_density, OxidizerStateError
        with pytest.raises(OxidizerStateError):
            _sessiz(get_oxidizer_density, 'peynir', 293.15)

    def test_n2o_bandi_disinda_sayi_uretmez(self):
        from hrma.app import get_oxidizer_density, OxidizerStateError
        for T in (90.0, 400.0):
            with pytest.raises(OxidizerStateError):
                _sessiz(get_oxidizer_density, 'n2o', T)

    def test_n2o_293K_literatur_degerinde(self):
        from hrma.app import get_oxidizer_density
        assert _sessiz(get_oxidizer_density, 'n2o', 293.15) == \
            pytest.approx(785.10, rel=1e-3)

    def test_lox_bant_ici_329_degil(self):
        """'329 değil' iddiası LOX'un BANT İÇİ sıcaklığında ölçülür.

        ÖH D17 / P7B4-04 (Fable-D15 ŞART). Eski hâli bu iddiayı
        293,15 K'de ölçüyor ve orada 1141,0'ı ``rel=1e-6`` ile
        ÇİVİLİYORDU. 293,15 K oksijenin kritik sıcaklığının (154,58 K)
        çok üstündedir: orada doymuş sıvı YOKTUR, dolayısıyla test
        bir kusuru — bant dışı ekstrapolasyonu — koruyor, kardeş N2O'da
        ZATEN uygulanan ``OxidizerStateError`` yolunun LOX'a
        genişletilmesini kırmızıya çeviriyordu.

        Ölçüm bandın içine taşındı: 90,19 K oksijenin normal kaynama
        noktasıdır ve kayıt orada meşrudur.
        """
        from hrma.app import get_oxidizer_density
        deger = _sessiz(get_oxidizer_density, 'lox', 90.19)
        assert deger != pytest.approx(329.0, abs=1.0)
        assert deger == pytest.approx(1141.0, rel=1e-6)

    def test_lox_293K_bant_disinda_1141_e_civilenmez(self):
        """293,15 K'de İKİ sonuç da kabul edilir; 1141,0 sabitlenmez.

        ÖH D17 / P7B4-04 (Fable-D15 ŞART). Bugün ölçülen (2 Eylül 2026,
        taban ``2426b4d``, ``docs/scofield/raw/OH/D17/app-api/a1/
        once_sart.json``): ``lox`` 90,19 / 154,6 / 293,15 K'nin ÜÇÜNDE de
        1141,0 — yani LOX'un ne sıcaklık bağımlılığı ne de bandı var,
        N2O'nunki ise var ([182,33; 309,52) K). Asimetrinin sahibi
        ``hrma/data/external_data_fetcher.py``, bu kulvarın sahası
        DEĞİL; bu bekçi yalnız İKİ yolu da meşru sayarak kapanışın
        önünü açar ve tek bir şeyi yasaklar: 329 sayısının geri
        gelmesini.
        """
        from hrma.app import get_oxidizer_density, OxidizerStateError
        try:
            deger = _sessiz(get_oxidizer_density, 'lox', 293.15)
        except OxidizerStateError:
            return
        assert deger != pytest.approx(329.0, abs=1.0)
