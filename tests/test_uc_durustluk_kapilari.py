"""v2.6.27 / A3 — uç katmanının dürüstlük kapıları.

Bu dosya, kullanıcının (Ayberk) hibrit motorda bulduğu rapor kalemlerinin
uç katmanına (``hrma/app.py``) düşen kısmını kilitler. Üç somut kusur, üçü
de HEAD üzerinde ÖLÇÜLDÜ (9 Ağustos 2026, bu düzeltmeler yazılmadan önce):

* **KALEM 1 — kazanılmamış yapısal hüküm.** Kullanıcı hiçbir yapısal bilgi
  göndermeden ``POST /calculate`` çağırdığında yanıt şunu diyordu::

      design_mode         : verify
      safety_factor_basis : verified against user-supplied wall thickness
      wall_thickness_used : 5,0 mm

  Kimse 5 mm vermemişti: ``app.py`` içindeki
  ``_mm_to_m(data.get('wall_thickness'), 0.005)`` çağrısı — o yardımcının
  sözleşmesi gereği ASLA ``None`` dönmez — her istekte bir sayı üretiyordu.
  Motor da ``wall_thickness_user_supplied = wall_thickness is not None``
  dediği için her koşuda ``True`` görüyor, yapısal modül DOĞRULAMA moduna
  geçiyordu. Aynı sessiz enjeksiyon malzemede de vardı
  (``or 'steel_4130'``). Motorun kendi yorumu doğru sözleşmeyi zaten
  yazıyordu; eksik olan, uç katmanının "verilmedi"yi üretmesiydi.

* **KALEM 2 — sessiz yanma süresi kırpması.** ``{thrust: 500,
  burn_time: 20, total_impulse: 7500}`` gönderildiğinde motor ``burn_time``
  alanını HİÇ okumuyor (toplam impuls + itki verildiğinde süre
  ``I/F = 15 s`` olarak ÇÖZÜLÜYOR). Ölçüldü: yanıtta ``burn_time = 15,0``,
  uyarı yok, ``defaults_used`` boş. Kullanıcının 20 s'i sessizce yok
  oluyordu. Beyan mekanizması (``_declare_overridden_inputs``) depoda
  hazırdı; alan yalnızca ``_CALCULATE_SOLVER_OWNED_FIELDS`` demetine
  girmemişti.

* **KALEM 3 — katıda enjekte edilen yanma hızı katsayıları.** ``app.py``
  ``burn_rate_a`` için 0,005 ve ``burn_rate_n`` için 0,35 varsayılanı
  koyuyordu. Bu çift, merkezî katalogun apcp kaydından 2,24 KAT sapar
  (referans basınçta 18,18 mm/s'ye karşı 8,12 mm/s) ve motor bunu KULLANICI
  girdisi sanıp ``warn.solid.burn_rate_off_catalog`` uyarısını ateşliyordu:
  kullanıcı, kendi girmediği bir sayı yüzünden uyarı alıyordu. Aynı sınıfın
  ikinci yüzü, kasa onayıydı: kullanıcı hiç kalınlık vermeden
  ``pressure_safety.vessel_status = 'PASS'`` dönüyordu — oysa cidarı
  HRMA'nın kendisi, o emniyet katsayısını sağlasın diye boyutlandırmıştı.

Testler hem ÇALIŞMA ZAMANI davranışını (Flask test istemcisi) hem de
kaynak metnini sınar: kusurun geri konması kaynakta olur.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

APP_PY = os.path.join(REPO_ROOT, 'hrma', 'app.py')

#: Doğrulayıcının geçmesi için gereken en küçük hibrit gövde. Bilerek
#: YAPISAL HİÇBİR ALAN taşımaz: kalemin ta kendisi "kullanıcı yapısal bilgi
#: vermedi" durumudur.
HIBRIT_YAPISAL_GIRDISIZ = {
    'motor_type': 'hybrid',
    'thrust': 1000,
    'burn_time': 10,
    'of_ratio': 6.0,
    'chamber_pressure': 20,
    'fuel_type': 'htpb',
    'oxidizer_type': 'n2o',
}

#: Katı motorun en küçük geometri gövdesi; yanma hızı katsayısı YOK.
#: (``propellant_type`` uçun zorunlu yakıt kimliği kapısını karşılar.)
KATI_KATSAYISIZ = {
    'chamber_diameter': 100,   # mm
    'grain_length': 500,       # mm
    'core_diameter': 30,       # mm
    'chamber_pressure': 40,    # bar
    'propellant_type': 'apcp',
}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _read_app_source():
    with open(APP_PY, encoding='utf-8') as handle:
        return handle.read()


def _calculate(client, **extra):
    payload = dict(HIBRIT_YAPISAL_GIRDISIZ)
    payload.update(extra)
    response = client.post('/calculate', json=payload,
                           headers={'Host': '127.0.0.1:8080'})
    assert response.status_code == 200, \
        response.get_data(as_text=True)[:400]
    return response.get_json()


def _solid(client, **extra):
    payload = dict(KATI_KATSAYISIZ)
    payload.update(extra)
    response = client.post('/calculate_solid', json=payload,
                           headers={'Host': '127.0.0.1:8080'})
    assert response.status_code == 200, \
        response.get_data(as_text=True)[:400]
    return response.get_json()


@pytest.fixture(scope='module')
def girdisiz(client):
    """Yapısal girdi GÖNDERİLMEMİŞ tek koşu (pahalı, bir kez)."""
    return _calculate(client)


@pytest.fixture(scope='module')
def cidarli(client):
    """Kullanıcı cidarı ve malzemeyi GERÇEKTEN vermiş koşu."""
    return _calculate(client, wall_thickness=5, chamber_material='steel_4130')


# ---------------------------------------------------------------------------
# KALEM 1 — yapısal hüküm kapısı
# ---------------------------------------------------------------------------
class TestKalem1YapisalHukumKapisi:

    def test_cidar_verilmeyince_dogrulama_iddiasi_yok(self, girdisiz):
        """Ölçülen kusurun birebir kendisi: 'verify' + 'user-supplied'."""
        chamber = girdisiz['motor']['structural_analysis']['chamber_analysis']
        assert chamber['design_mode'] == 'size', (
            'Kullanıcı cidar vermediği hâlde modül doğrulama modunda: '
            + str(chamber['design_mode']))
        assert chamber['wall_thickness_source'] == 'sized_by_hrma'
        assert chamber['safety_factor_is_tautological'] is True
        assert 'user-supplied' not in chamber['safety_factor_basis'], (
            'Kimsenin vermediği bir cidar "kullanıcının cidarı" diye '
            'sunuluyor: ' + chamber['safety_factor_basis'])

    def test_cidar_verilince_gercekten_dogrulaniyor(self, cidarli):
        """Karşı yön: gerçek girdi doğrulama modunu AÇMALI."""
        chamber = cidarli['motor']['structural_analysis']['chamber_analysis']
        assert chamber['design_mode'] == 'verify'
        assert chamber['wall_thickness_source'] == 'user_supplied'
        assert chamber['wall_thickness_used_mm'] == pytest.approx(5.0)
        assert chamber['safety_factor_is_tautological'] is False

    def test_hukmun_dayanagi_yanitta_duruyor(self, girdisiz):
        """``/analyze_structural_safety`` ile AYNI beyan sözleşmesi."""
        basis = girdisiz['structural_design_basis']
        assert basis['design_mode'] == 'size'
        assert basis['is_verification'] is False
        assert basis['wall_thickness_source'] == 'sized_by_hrma'
        assert basis['chamber_material_source'] == 'default:steel_4130'
        assert basis['verdict'] == 'withheld'
        assert 'safety_factor_is_tautological' in basis[
            'verdict_withheld_reasons']
        assert 'not a verification' in basis['message']

    def test_malzeme_secilince_beyan_degisiyor(self, cidarli):
        basis = cidarli['structural_design_basis']
        assert basis['chamber_material_source'] == 'user_supplied'
        assert basis['verdict'] == 'issued'
        assert basis['is_verification'] is True

    def test_totolojik_emniyet_katsayisi_isaretleniyor(self, girdisiz):
        """Sayı SİLİNMEZ (gerçekten hesaplandı) ama ne olduğu yazılır."""
        safety = girdisiz['motor']['structural_analysis']['safety_analysis']
        assert safety['minimum_safety_factor_is_tautological'] is True
        assert isinstance(safety['minimum_safety_factor'], (int, float))
        assert 'not an independent verification' in safety['verdict_basis']

    def test_onay_geri_cekilir_uyari_cekilmez(self):
        """Kapının asıl işi: ONAY tavana çekilir, TEHLİKE susturulmaz.

        Bu ayrım motorun gerçek bir koşusunda gösterilemez (hibrit hazne
        termal gerilme yüzünden zaten UNSAFE dönüyor), o yüzden kapı
        doğrudan, kurgulanmış bir yapısal sonuç sözlüğüyle sınanır.
        """
        from hrma.app import _motor_structural_design_basis

        def kur(status):
            return {'structural_analysis': {
                'chamber_analysis': {'design_mode': 'size',
                                     'safety_factor_is_tautological': True},
                'thermal_analysis': {
                    'wall_temperature_source': 'heat_transfer_module'},
                'safety_analysis': {'status': status, 'risk_level': 'LOW'},
            }}

        for onay in ('SAFE', 'ACCEPTABLE'):
            motor = kur(onay)
            basis = _motor_structural_design_basis(motor, None, None)
            safety = motor['structural_analysis']['safety_analysis']
            assert safety['status'] == 'NOT_EVALUATED', (
                f'{onay} kazanılmamışken yayımlandı')
            assert safety['risk_level'] == 'NOT_EVALUATED'
            assert basis['verdict'] == 'withheld'

        for uyari in ('MARGINAL', 'UNSAFE'):
            motor = kur(uyari)
            _motor_structural_design_basis(motor, None, None)
            assert motor['structural_analysis']['safety_analysis'][
                'status'] == uyari, (
                'Tehlike bildirimi susturuldu — kazanılmamış onaydan kötü')

    def test_cidar_sicakliginin_kaynagi_beyan_ediliyor(self, girdisiz):
        """Hesaplanmış sıcaklık ile "termal model kapalı" ayrılabilmeli."""
        thermal = girdisiz['motor']['structural_analysis']['thermal_analysis']
        assert thermal['wall_temperature_source'] == 'heat_transfer_module'
        assert thermal['thermal_model_ran'] is True

    def test_sicaklik_girdisi_yokken_termal_model_kapali_deniyor(self):
        """Yapısal modül tek başına: sıcaklık yoksa bunu SÖYLEMELİ."""
        from hrma.analysis.structural_analysis import StructuralAnalyzer

        sonuc = StructuralAnalyzer().analyze_structure({
            'chamber_pressure': 40, 'chamber_diameter': 0.1,
            'chamber_length': 0.5, 'throat_diameter': 0.02, 'burn_time': 10,
        })
        thermal = sonuc['thermal_analysis']
        assert thermal['wall_temperature_source'] == 'not_evaluated'
        assert thermal['thermal_model_ran'] is False

    def test_uc_katmani_artik_cidar_enjekte_etmiyor(self):
        """Kaynak bekçisi: varsayılan enjeksiyonu geri koyan fark görünür."""
        kaynak = _read_app_source()
        assert "_mm_to_m(data.get('wall_thickness'), 0.005)" not in kaynak, (
            'Cidar kalınlığı yine varsayılanla enjekte ediliyor; eksik girdi '
            'ile verilmiş girdi ayrımı çöker')
        assert "data.get('chamber_material') or 'steel_4130'" not in kaynak, (
            'Malzeme yine sessizce çeliğe çevriliyor')


# ---------------------------------------------------------------------------
# KALEM 2 — sessiz yanma süresi kırpması
# ---------------------------------------------------------------------------
class TestKalem2YanmaSuresiBeyani:

    def test_cozulen_sure_beyan_ediliyor(self, client):
        """Ölçülen kusur: 20 s gönderildi, 15 s kullanıldı, uyarı yoktu."""
        sonuc = _calculate(client, thrust=500, burn_time=20,
                           total_impulse=7500)
        assert sonuc['motor']['burn_time'] == pytest.approx(15.0), \
            'ölçüm dayanağı düştü: çözücü artık süreyi kırpmıyor olabilir'
        beyanlar = sonuc.get('inputs_not_used') or []
        alanlar = {b['field']: b for b in beyanlar}
        assert 'burn_time' in alanlar, (
            'Kullanıcının 20 s girdisi sessizce yok edildi; beyan yok')
        beyan = alanlar['burn_time']
        assert beyan['submitted'] == pytest.approx(20.0)
        assert beyan['used_by_model'] == pytest.approx(15.0)
        assert beyan['reason'] == 'solved_by_model'

    def test_cakisma_yokken_beyan_uretilmiyor(self, client):
        """Beyan VARSAYIMLA değil ÖLÇÜMLE üretilir: süre kullanıldıysa sus."""
        sonuc = _calculate(client, thrust=500, burn_time=20)
        assert sonuc['motor']['burn_time'] == pytest.approx(20.0)
        alanlar = {b['field'] for b in (sonuc.get('inputs_not_used') or [])}
        assert 'burn_time' not in alanlar, (
            'Gerçekten kullanılan girdi "kullanılmadı" diye beyan ediliyor')

    def test_alan_solver_owned_demetinde(self):
        from hrma.app import _CALCULATE_SOLVER_OWNED_FIELDS
        assert 'burn_time' in _CALCULATE_SOLVER_OWNED_FIELDS


# ---------------------------------------------------------------------------
# KALEM 3 — katı yanma hızı katsayıları ve kasa onayı
# ---------------------------------------------------------------------------
class TestKalem3KatiKatsayiKaynagi:

    def test_katsayi_verilmeyince_katalogdan_cozuluyor(self, client):
        """Uç katmanı 0,005 / 0,35 uydurmuyor; katalog kaydı kullanılıyor."""
        from hrma.engines.solid_rocket_engine import _catalog_burn_rate

        sonuc = _solid(client, propellant_type='apcp')
        girdiler = sonuc['burn_rate_inputs']
        a_kat, n_kat = _catalog_burn_rate('apcp')
        assert girdiler['burn_rate_a_source'] == 'central_catalog:apcp'
        assert girdiler['burn_rate_n_source'] == 'central_catalog:apcp'
        assert girdiler['burn_rate_a_used'] == pytest.approx(float(a_kat))
        assert girdiler['burn_rate_n_used'] == pytest.approx(float(n_kat))
        # Enjekte edilen eski değerin geri gelmediği ayrıca sınanır:
        # 0,005 katalogtan 2,24 kat sapıyordu.
        assert girdiler['burn_rate_a_used'] != pytest.approx(0.005)

    def test_katsayi_secilen_yakita_ait(self, client):
        """APCP'nin katsayısı KNDX'e verilmez (kurucu varsayılanı APCP'dir)."""
        from hrma.engines.solid_rocket_engine import _catalog_burn_rate

        sonuc = _solid(client, propellant_type='kndx')
        girdiler = sonuc['burn_rate_inputs']
        a_kndx, n_kndx = _catalog_burn_rate('kndx')
        assert girdiler['burn_rate_a_source'] == 'central_catalog:kndx'
        assert girdiler['burn_rate_a_used'] == pytest.approx(float(a_kndx))
        assert girdiler['burn_rate_n_used'] == pytest.approx(float(n_kndx))

    def test_kullanicinin_katsayisi_ezilmiyor(self, client):
        sonuc = _solid(client, propellant_type='apcp', burn_rate_a=0.005,
                       burn_rate_n=0.35)
        girdiler = sonuc['burn_rate_inputs']
        assert girdiler['burn_rate_a_source'] == 'request'
        assert girdiler['burn_rate_n_source'] == 'request'
        assert girdiler['burn_rate_a_used'] == pytest.approx(0.005)

    def test_katalog_disi_uyarisi_artik_kullaniciya_ait(self, client):
        """Kullanıcı hiçbir katsayı vermediyse "katalog dışısın" denmez."""
        def kodlar(sonuc):
            return {u.get('code') if isinstance(u, dict) else u
                    for u in (sonuc.get('design_warnings') or [])}

        girdisiz_sonuc = _solid(client, propellant_type='apcp')
        assert 'warn.solid.burn_rate_off_catalog' not in kodlar(
            girdisiz_sonuc), (
            'Kullanıcı katsayı vermemişken uç katmanının kendi enjeksiyonu '
            'yüzünden "katalog dışı" uyarısı alıyor')
        # Gerçekten sapan bir değer GİRİLİRSE uyarı yerinde durmalı.
        sapmali = _solid(client, propellant_type='apcp', burn_rate_a=0.005,
                         burn_rate_n=0.35)
        assert 'warn.solid.burn_rate_off_catalog' in kodlar(sapmali), (
            'Gerçek sapma artık uyarılmıyor — uyarı susturulmuş olabilir')

    def test_uc_katmani_artik_katsayi_enjekte_etmiyor(self):
        kaynak = _read_app_source()
        assert "data.get('burn_rate_a', 0.005)" not in kaynak
        assert "data.get('burn_rate_n', 0.35)" not in kaynak


class TestKalem3KasaOnayKapisi:

    def test_kalinlik_verilmeyince_kap_onayi_yok(self, client):
        """Ölçülen kusur: dört basınçta da ``vessel_status = 'PASS'``."""
        # Onay listesi UYGULAMANIN kendi tanımından okunur; testin kendi
        # kopyasını tutması iki kaynağın ayrışmasına yol açardı.
        from hrma.app import _VESSEL_APPROVAL_VERDICTS

        press = _solid(client)['safety_analysis']['pressure_safety']
        assert press['vessel_status'] not in _VESSEL_APPROVAL_VERDICTS, (
            'Kendi boyutlandırdığı cidarı sınayıp onay veriyor: '
            + str(press['vessel_status']))
        assert press['vessel_status'] == 'NOT_EVALUATED'
        assert press['vessel_status_is_tautological'] is True
        assert press['wall_thickness_source'] == 'sized_by_hrma'
        assert 'not an independent verification' in press[
            'vessel_status_basis']

    def test_hesaplanan_sayilar_silinmiyor(self, client):
        """Onay geri çekilir, ÖLÇÜM değil: kopma basıncı ve marj kalır."""
        press = _solid(client)['safety_analysis']['pressure_safety']
        for alan in ('burst_pressure_bar', 'burst_margin',
                     'case_wall_thickness_mm', 'design_pressure_bar'):
            assert isinstance(press[alan], (int, float)), alan
            assert press[alan] > 0, alan

    def test_kalinlik_verilince_onay_veriliyor(self, client):
        press = _solid(client, case_thickness=3.0)[
            'safety_analysis']['pressure_safety']
        assert press['wall_thickness_source'] == 'user_supplied'
        assert press['vessel_status_is_tautological'] is False
        assert press['vessel_status'] == 'PASS'
        assert press['case_wall_thickness_mm'] == pytest.approx(3.0)

    def test_tehlike_bildirimi_susturulmuyor(self):
        """FAIL/MARGINAL asla 'değerlendirilmedi'ye çevrilmez."""
        from hrma.app import _withhold_unearned_vessel_verdict

        for uyari in ('FAIL', 'MARGINAL'):
            sonuc = {'safety_analysis': {
                'pressure_safety': {'vessel_status': uyari}}}
            _withhold_unearned_vessel_verdict(sonuc,
                                              case_thickness_supplied=False)
            assert sonuc['safety_analysis']['pressure_safety'][
                'vessel_status'] == uyari
