"""ÖH Dalga-18 · kulvar app-api, aşama 1 — onarım bekçileri.

Her sınıf TEK bir defter kalemini bağlar ve ters-mutasyonla kırmızıya
döndüğü ÖLÇÜLMÜŞTÜR (kanıt: ``docs/scofield/raw/OH/D18/app-api/a1/``).

- ``P10B2-05`` (Fable-D16 ŞARTI) — CSV birim beyanı FAIL-CLOSED değildi:
  kullanıcı ``Thrust (lbs)`` yazdığında künye ``declared: null`` +
  ``source: 'assumed (no unit declared)'`` basıyor ve TEK uyarı bile
  çıkmıyordu. 100 lbs (= 444,82 N) sessizce 100 N sayılıyordu.
- ``P12aB3-01`` (Fable-D16 ŞARTI) — ``inputs_not_used`` beyanının EKRANA
  BASILAN kanala yansıtılması yalnız iki gerekçeyi tanıyordu; ürünün en
  çok ürettiği üçüncü gerekçe (``solver_owned_output_name``) eşlemede yok
  ve eşlenmeyen gerekçe ``continue`` ile SUSTURULUYORDU.
- ``OH-D16-10`` — ``/api/solid-monte-carlo`` aynı ret sınıfı için iki ad
  döndürüyordu (``invalid_solid_monte_carlo_input`` ⟷
  ``solid_input_rejected``).
- ``P7B3-03`` — ``/api/generate-3d`` paket ucu sunucu geçici dizinlerini
  silmiyordu (üçüncü ayak; ilk iki ayak D15 a2'de kapandı).
"""

import json
import os

import pytest

from hrma.app import app
from hrma.validation.user_data_validation import parse_thrust_csv


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# P10B2-05 ŞARTI — TANINMAYAN BİRİM FAIL-CLOSED
# ---------------------------------------------------------------------------
class TestP10B2_05TaninmayanBirim:
    """Beyan VARSA ürün 'beyan yok' diyemez.

    Taban ölçümü (``once_a1.json``): ``Thrust (lbs)`` / ``Thrust (lb)`` /
    ``Time (min)`` üçünde de ``declared: null``,
    ``source: 'assumed (no unit declared)'``, ``warnings: []``.
    """

    @pytest.mark.parametrize('metin,rol,ham', [
        ("Time (s),Thrust (lbs)\n0,0\n1,100\n2,0\n", 'thrust', 'lbs'),
        ("Time (s),Thrust (lb)\n0,0\n1,100\n2,0\n", 'thrust', 'lb'),
        ("Time (min),Thrust (N)\n0,0\n1,100\n2,0\n", 'time', 'min'),
        # ÖH D20 — Fable-D18 ŞARTI. Taban 14acd1d'de bu iki başlıkta
        # ``declared_raw=None``, ``source='assumed (no unit declared)'``,
        # uyarı 0 idi (``once.json``): elle yazılmış ``_UNIT_RAW_MAX_LEN=6``
        # tavanı, tanınan birimlerin en uzunundan (7: 'newtons'/'seconds')
        # KISAYDI ve beyanı yutuyordu. 'minutes' 60x sessiz hata demektir.
        ("Time (s),Thrust (kilonewton)\n0,0\n1,100\n2,0\n",
         'thrust', 'kilonewton'),
        ("Time (minutes),Thrust (N)\n0,0\n1,100\n2,0\n", 'time', 'minutes'),
    ])
    def test_taninmayan_baslik_birimi_uyari_basar(self, metin, rol, ham):
        out = parse_thrust_csv(metin)
        kunye = out['units'][rol]
        assert kunye['declared'] is None, 'tanınmayan token çevrilmemeli'
        assert kunye['declared_raw'] == ham, (
            f'beyan kaybolmuş: {kunye!r}')
        assert kunye['source'] == 'header (unrecognized)', kunye
        assert 'no unit declared' not in kunye['source'], (
            "beyan VARKEN 'no unit declared' cümlesi basılamaz")
        uyarilar = [w for w in out['warnings']
                    if ham in w and 'not recognized' in w]
        assert uyarilar, (
            f'tanınmayan birim sessizce yutuldu; uyarılar: {out["warnings"]}')
        # Bilinen birimler kullanıcıya adıyla söylenir (TEK KAYNAK: tablo)
        from hrma.validation.user_data_validation import _UNIT_FACTOR_TABLE
        assert f'known {rol} units' in uyarilar[0], uyarilar[0]
        for bilinen in _UNIT_FACTOR_TABLE[rol]:
            assert bilinen in uyarilar[0], (
                f"'{bilinen}' bilinen birimler listesinden düşmüş: "
                f'{uyarilar[0]}')

    def test_taninmayan_birim_sayiyi_uydurmaz(self):
        """Fail-closed'un diğer yüzü: çevrim UYDURULMAZ, sayı aynen kalır."""
        out = parse_thrust_csv("Time (s),Thrust (lbs)\n0,0\n1,100\n2,0\n")
        assert out['thrust'].max() == pytest.approx(100.0)
        assert out['units']['thrust']['factor_applied'] == 1.0

    def test_birim_satirindaki_taninmayan_token_da_bildirilir(self):
        out = parse_thrust_csv("time;thrust\ns;lbs\n0;0\n1;100\n2;0\n")
        kunye = out['units']['thrust']
        assert kunye['declared_raw'] == 'lbs', kunye
        assert kunye['source'] == 'unit row (unrecognized)', kunye
        assert any('lbs' in w and 'not recognized' in w
                   for w in out['warnings']), out['warnings']

    def test_baslik_ve_birim_satiri_celisirse_uyari(self):
        """İki beyan çelişiyorsa kullanıcı bunu ÖĞRENİR (taban: sessiz)."""
        out = parse_thrust_csv(
            "Time (s),Thrust (kgf)\ns,N\n0,0\n1,100\n2,0\n")
        celiski = [w for w in out['warnings']
                   if 'declared twice' in w and 'kgf' in w and "'n'" in w]
        assert celiski, out['warnings']
        # Birim satırı kazanır (daha açık beyandır) — davranış korunur
        assert out['units']['thrust']['declared'] == 'n'
        assert out['thrust'].max() == pytest.approx(100.0)

    def test_beyansiz_dosya_hala_sessiz(self):
        """Yanlış alarm yok: beyan YOKSA uyarı da yok."""
        out = parse_thrust_csv("time,thrust\n0,0\n1,100\n2,0\n")
        assert out['warnings'] == []
        assert out['units']['thrust']['declared_raw'] is None
        assert out['units']['thrust']['source'] == 'assumed (no unit declared)'

    def test_taninan_birim_ceviriyi_surduruyor(self):
        """D16 onarımı bozulmadı: kgf hâlâ SI'ya çevriliyor."""
        out = parse_thrust_csv("Time (s),Thrust (kgf)\n0,0\n1,100\n2,0\n")
        assert out['thrust'].max() == pytest.approx(980.665, rel=1e-12)
        assert out['units']['thrust']['source'] == 'header'

    def test_uzun_parantez_icerigi_birim_sayilmaz(self):
        """``'Thrust (peak run 3)'`` yanlış alarm üretmez."""
        out = parse_thrust_csv(
            "Time (s),Thrust (peak run 3)\n0,0\n1,100\n2,0\n")
        assert out['units']['thrust']['declared_raw'] is None
        assert not any('not recognized' in w for w in out['warnings'])

    def test_ucta_declared_raw_yayimlanir(self, istemci):
        r = istemci.post('/api/validation/upload-csv',
                         json={'csv_text':
                               "Time (s),Thrust (lbs)\n0,0\n1,100\n2,0\n"})
        assert r.status_code == 200
        birimler = r.get_json()['parsed']['units']
        assert birimler['thrust']['declared_raw'] == 'lbs'
        assert birimler['thrust']['source'] == 'header (unrecognized)'


# ---------------------------------------------------------------------------
# P12aB3-01 ŞARTI — beyan EKRANA basılan kanala her gerekçeyle ulaşır
# ---------------------------------------------------------------------------
_KATI_YUK = {
    'motor_name': 'BEKCI-KATI', 'propellant_type': 'apcp',
    'grain_type': 'bates', 'chamber_pressure': 40.0,
    'thrust': 5000.0, 'burn_time': 3.0,
    'chamber_diameter': 100.0, 'grain_length': 500.0,
    'core_diameter': 30.0, 'expansion_ratio': 8.0,
    'chamber_temperature': 3000.0,
}
_SIVI_YUK = {
    'motor_name': 'BEKCI-SIVI', 'thrust': 10000.0, 'burn_time': 30.0,
    'chamber_pressure': 30.0, 'mixture_ratio': 2.2,
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'expansion_ratio': 12.0,
    'chamber_temperature': 3000.0, 'tank_pressure': 55.0,
    # ÖH D27 / OH-D26-12 — ÖNERME AÇIK YAZILIYOR (gövde çevrildi).
    # Bu gövde ``tank_pressure`` gönderiyor ve testin iddiası "kabul edilen
    # ama okunmayan alanın beyanı ekrana ulaşır"dır. Çevrim yazılmadığı
    # için uç turbopompalı varsayılana düşüyordu; orada tank enjektörü
    # BESLEMEZ ve alan artık adıyla reddediliyor (422), yani gövde 200
    # dönmeyeceği için testin ölçtüğü beyan kanalı HİÇ doğmazdı (ve
    # ``test_her_beyan_ekrana_ulasir_oran_tam`` boş listeyle SESSİZCE
    # geçerdi). Çevrim ilan edilince tank gerçekten enjektör beslemesidir,
    # istek 200 döner ve beyan zinciri eskisi gibi ölçülür.
    'engine_cycle': 'pressure_fed',
}


def _ekran_kanallari(govde):
    """app.js::collectResultWarnings (app.js:1620-1629) ile AYNI üç kanal."""
    motor = govde.get('motor') or {}
    enjektor = govde.get('injector') or {}
    kayitlar = []
    for kanal in ((motor.get('warnings') or motor.get('design_warnings')) or [],
                  motor.get('input_warnings') or govde.get('input_warnings')
                  or [], (enjektor.get('warnings')) or []):
        if isinstance(kanal, list):
            kayitlar.extend(kanal)
    return kayitlar


def _kayit_metni(k):
    if isinstance(k, str):
        return k
    if isinstance(k, dict):
        p = k.get('params') if isinstance(k.get('params'), dict) else {}
        return ' '.join(str(v) for v in (k.get('code'), k.get('message'),
                                         k.get('text'), k.get('fallback'),
                                         p.get('field')) if v)
    return ''


class TestP12aB3_01BeyanHerGerekceyleEkranda:
    """Taban ölçümü (``once_a1.json``): katı **0/1**, sıvı **1/3**."""

    @pytest.mark.parametrize('yol,yuk,beklenen', [
        ('/calculate_solid', _KATI_YUK, {'chamber_temperature'}),
        ('/calculate_liquid', _SIVI_YUK,
         {'chamber_temperature', 'tank_pressure'}),
    ])
    def test_solver_owned_beyani_ekrana_ulasir(self, istemci, yol, yuk,
                                               beklenen):
        r = istemci.post(yol, json=yuk)
        assert r.status_code == 200, r.status_code
        govde = r.get_json()
        beyanlar = govde.get('inputs_not_used') or []
        alanlar = {b.get('field') for b in beyanlar}
        assert beklenen <= alanlar, (
            f'beyan hiç üretilmemiş; üretilenler: {sorted(alanlar)}')
        metinler = [_kayit_metni(k) for k in _ekran_kanallari(govde)]
        for alan in beklenen:
            assert any(alan in m for m in metinler), (
                f"'{alan}' beyanı ekrana basılan kanala ULAŞMIYOR; "
                f'kanal: {metinler}')

    def test_her_beyan_ekrana_ulasir_oran_tam(self, istemci):
        """Tam sayım: üretilen HER beyan ekranda anılır (n/n)."""
        r = istemci.post('/calculate_liquid', json=_SIVI_YUK)
        govde = r.get_json()
        beyanlar = govde.get('inputs_not_used') or []
        metinler = [_kayit_metni(k) for k in _ekran_kanallari(govde)]
        kayip = [b.get('field') for b in beyanlar
                 if not any(b.get('field') in m for m in metinler)]
        assert not kayip, f'ekrana ulaşmayan beyan: {kayip}'

    def test_taninmayan_gerekce_susturulmaz(self):
        """FAIL-CLOSED: eşlemede olmayan gerekçe de kanala girer."""
        from hrma.app import (_beyanlari_uyari_kanalina_yansit,
                              _INPUT_NOT_USED_GENERIC_WARN_CODE)
        sonuclar = {}
        _beyanlari_uyari_kanalina_yansit(sonuclar, [{
            'field': 'uydurma_alan',
            'submitted': 1.0,
            'used_by_model': 2.0,
            'reason': 'bu_gerekce_eslemede_yok',
            'message': 'ölçülmüş cümle',
        }])
        kanal = sonuclar.get('input_warnings') or []
        assert len(kanal) == 1, kanal
        assert kanal[0]['code'] == _INPUT_NOT_USED_GENERIC_WARN_CODE
        assert kanal[0]['fallback'] == 'ölçülmüş cümle'
        assert kanal[0]['params']['field'] == 'uydurma_alan'

    def test_eslemede_gercek_gerekce_var(self):
        from hrma.app import _INPUT_NOT_USED_WARN_CODES
        assert 'solver_owned_output_name' in _INPUT_NOT_USED_WARN_CODES

    def test_kod_i18n_sozlugunde_karsiliksiz_degil(self):
        """Eşlenen kodun TR+EN karşılığı sözlükte GERÇEKTEN duruyor."""
        from hrma.app import _INPUT_NOT_USED_WARN_CODES
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sozluk = open(os.path.join(kok, 'hrma/static/js/i18n_common.js'),
                      encoding='utf-8').read()
        kod = _INPUT_NOT_USED_WARN_CODES['solver_owned_output_name']
        assert sozluk.count(f"'{kod}'") >= 2, (
            f'{kod} iki dilde de tanımlı değil')


# ---------------------------------------------------------------------------
# OH-D16-10 — /api/solid-monte-carlo TEK RET ADI
# ---------------------------------------------------------------------------
_MC_TABAN = {'motor_name': 'MC', 'propellant_type': 'apcp',
             'grain_type': 'bates', 'chamber_pressure': 40.0,
             'thrust': 5000.0, 'burn_time': 3.0,
             'chamber_diameter': 100.0, 'grain_length': 500.0,
             'core_diameter': 30.0, 'expansion_ratio': 8.0, 'n_samples': 8}


class TestOHD16_10TekRetAdi:
    """Taban ölçümü (``once_a1.json``): AYNI uç iki ad döndürüyordu —
    ``core_diameter`` / ``chamber_pressure`` -> ``invalid_solid_monte_
    carlo_input``, ``burn_rate_a`` -> ``solid_input_rejected``."""

    @pytest.mark.parametrize('ek,kapı', [
        ({'core_diameter': -5.0}, 'endpoint_input_gate'),
        ({'chamber_pressure': -3.0}, 'endpoint_input_gate'),
        ({'burn_rate_a': -1.0}, 'solid_engine_constructor'),
        ({'core_diameter': -5.0, 'burn_rate_a': -1.0}, 'endpoint_input_gate'),
        ({'core_diameter': 99.0}, 'endpoint_core_wall_margin_gate'),
        ({'thrust': 'abc'}, 'band_gate'),
    ])
    def test_ret_adi_tek(self, istemci, ek, kapı):
        from hrma.app import SOLID_MC_REJECT_ERROR
        r = istemci.post('/api/solid-monte-carlo',
                         json=dict(_MC_TABAN, **ek))
        assert r.status_code == 422, r.status_code
        govde = r.get_json()
        assert govde['error'] == SOLID_MC_REJECT_ERROR, govde['error']
        assert govde['rejected_by'] == kapı, govde.get('rejected_by')
        assert govde.get('invalid_fields'), govde

    def test_ret_adlari_kumesi_tekil(self, istemci):
        """Dört bozuk gövde -> TEK ad (taban: iki ad)."""
        adlar = set()
        for ek in ({'core_diameter': -5.0}, {'burn_rate_a': -1.0},
                   {'chamber_pressure': -3.0},
                   {'core_diameter': -5.0, 'burn_rate_a': -1.0}):
            r = istemci.post('/api/solid-monte-carlo',
                             json=dict(_MC_TABAN, **ek))
            adlar.add(r.get_json().get('error'))
        assert len(adlar) == 1, f'uç hâlâ birden çok ret adı basıyor: {adlar}'

    def test_kaynak_kapi_bilgisi_kaybolmadi(self, istemci):
        """Ad birleşti ama hangi kapının ateşlendiği KAYBOLMADI."""
        r = istemci.post('/api/solid-monte-carlo',
                         json=dict(_MC_TABAN, burn_rate_a=-1.0))
        govde = r.get_json()
        assert govde['error_type'] == 'SolidGeometryError'
        assert govde['invalid_fields'][0]['field'] == 'burn_rate_a'

    def test_gecerli_govde_hala_200(self, istemci):
        r = istemci.post('/api/solid-monte-carlo', json=dict(_MC_TABAN))
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        assert r.get_json()['status'] == 'success'


# ---------------------------------------------------------------------------
# P7B3-03 (üçüncü ayak) — geçici dizinin YAŞ sınırı
# ---------------------------------------------------------------------------
_PAKET_GEO = {'motor_type': 'hybrid', 'chamber_diameter': 0.1,
              'chamber_length': 0.3, 'port_diameter': 0.05,
              'throat_diameter': 0.02, 'exit_diameter': 0.04}


class TestP7B3_03IndirmePenceresi:
    """Taban ölçümü (``once_p7b303.json``): 6 çağrı -> 6 geçici dizin /
    3.380.712 bayt, defterde 18 kayıt, ``_STL_REGISTRY_TTL_S`` YOK — yani
    sınır yalnız SAYIYA bağlıydı ve disk süresiz duruyordu."""

    def test_pencere_tek_kaynakta_tanimli(self):
        from hrma import app as app_modul
        assert isinstance(app_modul._STL_REGISTRY_TTL_S, float)
        assert app_modul._STL_REGISTRY_TTL_S > 0

    def test_paket_ucu_pencereyi_beyan_eder(self, istemci):
        from hrma import app as app_modul
        r = istemci.post('/api/generate-complete-package',
                         json={'motor_data': dict(_PAKET_GEO),
                               'package_options':
                                   {'include_openrocket': False}})
        assert r.status_code == 200, r.status_code
        cad = (r.get_json().get('complete_package') or {}).get('cad') or {}
        assert cad.get('stl_files'), 'paket STL üretmedi'
        assert cad['stl_download_window_s'] == app_modul._STL_REGISTRY_TTL_S
        # sunucunun geçici yolu HÂLÂ sızmıyor (D15 ayakları korunur)
        import tempfile as _tf
        tmp = _tf.gettempdir()
        assert not any(str(p).startswith(tmp) for p in cad['stl_files'])

    def test_penceresi_dolan_kayit_silinir_ve_410_doner(self, istemci,
                                                        monkeypatch):
        """Yaş sınırı GERÇEKTEN uygulanıyor: kayıt düşer, dizin gider,
        jeton eski bir dosyayla İKAME EDİLMEZ."""
        import tempfile as _tf
        from hrma import app as app_modul

        r = istemci.post('/api/generate-complete-package',
                         json={'motor_data': dict(_PAKET_GEO),
                               'package_options':
                                   {'include_openrocket': False}})
        cad = (r.get_json().get('complete_package') or {}).get('cad') or {}
        jeton = os.path.basename(cad['stl_files'][0])
        yol = app_modul._STL_DOWNLOAD_REGISTRY[jeton]
        dizin = os.path.dirname(yol)
        assert os.path.isdir(dizin)
        assert istemci.get('/download/stl/' + jeton).status_code == 200

        # Pencereyi sıfırla: bütün kayıtlar "eski" sayılır.
        monkeypatch.setattr(app_modul, '_STL_REGISTRY_TTL_S', -1.0)
        dusen = app_modul._stl_defterini_yasa_gore_supur()
        assert dusen >= 1, 'yaşa göre süpürme hiçbir kaydı düşürmedi'
        assert jeton not in app_modul._STL_DOWNLOAD_REGISTRY
        assert not os.path.isdir(dizin), 'geçici dizin hâlâ diskte'

        r2 = istemci.get('/download/stl/' + jeton)
        assert r2.status_code == 410, r2.status_code
        j = r2.get_json()
        assert j['error'] == 'stl_download_window_expired', j
        assert j['window_s'] == -1.0

    def test_indirme_ucu_supurmeyi_KENDI_kosturur(self, istemci, monkeypatch):
        """ÖH D20 — Fable-D18 ŞARTI (M11 kesiti).

        Süpürme ELLE ÇAĞRILMAZ: yalnız ``_STL_REGISTRY_TTL_S`` geçmişe
        çekilir ve doğrudan ``GET /download/stl/<jeton>`` atılır. Kırmızıya
        döndürdüğü mutasyon: ``download_stl_file`` içindeki
        ``_stl_defterini_yasa_gore_supur()`` çağrısının silinmesi (Fable-D18
        ölçümünde bu mutasyon sınıfı 5/5 YEŞİL bırakıyordu — pencere yalnız
        kâğıtta kalıyordu). Kanıt:
        ``docs/scofield/raw/OH/D20/app-api/a1/mutasyon.json`` (M-D20-2).
        """
        from hrma import app as app_modul

        r = istemci.post('/api/generate-complete-package',
                         json={'motor_data': dict(_PAKET_GEO),
                               'package_options':
                                   {'include_openrocket': False}})
        cad = (r.get_json().get('complete_package') or {}).get('cad') or {}
        jeton = os.path.basename(cad['stl_files'][0])
        dizin = os.path.dirname(app_modul._STL_DOWNLOAD_REGISTRY[jeton])
        assert os.path.isdir(dizin)

        monkeypatch.setattr(app_modul, '_STL_REGISTRY_TTL_S', -1.0)
        # ---- BURADAN SONRA SÜPÜRME ELLE ÇAĞRILMAZ ----
        r2 = istemci.get('/download/stl/' + jeton)
        assert r2.status_code == 410, (
            'indirme ucu kendi süpürmesini koşturmuyor: süresi dolmuş '
            f'bağlantı {r2.status_code} döndü')
        j = r2.get_json()
        assert j['error'] == 'stl_download_window_expired', j
        assert j['reason'] == app_modul._STL_DUSME_PENCERE, j
        assert jeton not in app_modul._STL_DOWNLOAD_REGISTRY
        assert not os.path.isdir(dizin), (
            'geçici dizin uçtan tetiklenen süpürmede silinmedi')

    def test_sayi_siniriyla_dusen_jeton_da_ikame_edilmez(self, tmp_path,
                                                         monkeypatch,
                                                         istemci):
        """ÖH D20 — Fable-D18 ŞARTI (isteğe bağlı ayak).

        Taban ölçümü (``once.json``): defter tavanı aşılınca düşen jeton
        ``_STL_EXPIRED_TOKENS``'a YAZILMIYORDU; ``GET /download/stl/<jeton>``
        ``cad_exports/`` yoluna düşüp 404 'File not found' veriyordu — aynı
        adlı bir dosya orada varsa BAŞKA bir katı sunulabilirdi. İki düşme
        yolu artık aynı doktrini uyguluyor.
        """
        from hrma import app as app_modul

        def _kayit(ad):
            d = tmp_path / ad
            d.mkdir()
            f = d / (ad + '.stl')
            f.write_text('solid a\nendsolid a\n')
            return app_modul._register_stl_download(str(f))

        monkeypatch.setattr(app_modul, '_STL_REGISTRY_MAX', 2)
        ilk = _kayit('bir')
        _kayit('iki')
        _kayit('uc')          # tavan aşıldı -> 'ilk' SAYI sınırıyla düşer

        assert ilk not in app_modul._STL_DOWNLOAD_REGISTRY
        assert (app_modul._STL_EXPIRED_TOKENS.get(ilk)
                == app_modul._STL_DUSME_DEFTER_TAVANI), (
            'sayı sınırıyla düşen jeton "artık yok" defterine yazılmadı')
        r = istemci.get('/download/stl/' + ilk)
        assert r.status_code == 410, (
            f'sayı sınırıyla düşen jeton {r.status_code} döndü (ikame riski)')
        j = r.get_json()
        assert j['error'] == 'stl_download_window_expired', j
        assert j['reason'] == app_modul._STL_DUSME_DEFTER_TAVANI, j
        # Sebep DOĞRU söylenir: bu bağlantı yaşlanmadı, yer açıldı.
        assert 'expired' not in j['message'].lower(), j['message']
        assert str(app_modul._STL_REGISTRY_MAX) in j['message'], j['message']

    def test_defter_ve_zaman_sozlugu_ayni_boyda(self, istemci):
        from hrma import app as app_modul
        istemci.post('/api/generate-complete-package',
                     json={'motor_data': dict(_PAKET_GEO),
                           'package_options': {'include_openrocket': False}})
        assert (set(app_modul._STL_DOWNLOAD_REGISTRY)
                == set(app_modul._STL_REGISTRY_TIMES)), (
            'iki sözlük ayrıştı; yaş sınırı bazı kayıtlara uygulanmaz')

    def test_yeni_kayit_eskiyi_yasa_gore_supurur(self, monkeypatch, tmp_path):
        """Süpürme KAYIT yolunda da tetiklenir (uç çağrısına bağlı değil).

        Ters-mutasyon notu: bu bekçi olmadan ``_register_stl_download``
        içindeki süpürme çağrısı silinse bile sınıf yeşil kalıyordu
        (ölçüldü, ``mutasyon_P7B3-03.json`` ilk satır) — çünkü diğer
        testler süpürmeyi ya doğrudan ya indirme ucundan çağırıyor.
        """
        from hrma import app as app_modul

        eski_dizin = tmp_path / 'hrma_stl_eski'
        eski_dizin.mkdir()
        eski_dosya = eski_dizin / 'motor_assembly.stl'
        eski_dosya.write_text('solid x\nendsolid x\n')
        monkeypatch.setattr(app_modul.tempfile, 'gettempdir',
                            lambda: str(tmp_path))
        jeton_eski = app_modul._register_stl_download(str(eski_dosya))
        assert jeton_eski in app_modul._STL_DOWNLOAD_REGISTRY

        # Pencereyi geçmişe al ve YALNIZCA yeni bir kayıt yap.
        monkeypatch.setattr(app_modul, '_STL_REGISTRY_TTL_S', -1.0)
        yeni_dizin = tmp_path / 'hrma_stl_yeni'
        yeni_dizin.mkdir()
        yeni_dosya = yeni_dizin / 'chamber.stl'
        yeni_dosya.write_text('solid y\nendsolid y\n')
        app_modul._register_stl_download(str(yeni_dosya))

        assert jeton_eski not in app_modul._STL_DOWNLOAD_REGISTRY, (
            'kayıt yolu yaşa göre süpürmüyor')
        assert not eski_dizin.exists(), 'süresi dolan geçici dizin silinmedi'


# ---------------------------------------------------------------------------
# P7B3-23 — hüküm alıkonmuşken "bu bir doğrulamadır" cümlesi
# ---------------------------------------------------------------------------
class TestP7B3_23DurustlukCumlesi:
    """Taban ölçümü (``once_p7b323.json``, kalemin KENDİ repro gövdesi —
    50 bar / Ø100 mm, kullanıcı cidarı verilmiş):

    | cidar | verdict | design_basis.message | min SF ⟷ kazanılmış |
    |---|---|---|---|
    | 2,5 mm | withheld | "... this result is a verification." | 3,057 ⟷ 3,057 |
    | 5,0 mm | withheld | aynı cümle | 4,0 ⟷ 6,115 |
    | 45,0 mm | withheld | aynı cümle | 4,0 ⟷ 25,458 |

    Kalemin BİRİNCİ iddiası (``verdict='issued'``) ölü: hüküm artık
    alıkonuyor. İKİNCİ iddiası canlıydı: aynı yanıt hem "this result is a
    verification" hem "No acceptance is issued" diyordu.
    """

    @staticmethod
    def _yanit(istemci, t_mm):
        r = istemci.post('/analyze_structural_safety', json={
            'chamber_pressure': 50, 'chamber_diameter': 0.1,
            'chamber_length': 0.5, 'throat_diameter': 0.02,
            'burn_time': 10, 'material': 'steel_4130',
            'wall_thickness': t_mm / 1000.0})
        assert r.status_code == 200, r.status_code
        return r.get_json()

    @pytest.mark.parametrize('t_mm', [2.5, 5.0, 20.0, 45.0])
    def test_hukum_alikonmusken_kosulsuz_dogrulama_cumlesi_yok(
            self, istemci, t_mm):
        j = self._yanit(istemci, t_mm)
        db = j['design_basis']
        assert db['verdict'] == 'withheld', db['verdict']
        mesaj = db['message']
        assert 'this result is a verification.' not in mesaj, (
            'hüküm ALIKONMUŞKEN koşulsuz doğrulama cümlesi basılıyor: '
            f'{mesaj!r}')
        assert 'No acceptance is issued' in mesaj, mesaj

    def test_ayni_yanitta_celiski_kalmadi(self, istemci):
        """Yanıtın HER metni taranır: 'is a verification' iddiası ile
        'No acceptance is issued' aynı gövdede çelişemez."""
        j = self._yanit(istemci, 45.0)
        metinler = []

        def _gez(x):
            if isinstance(x, str):
                metinler.append(x)
            elif isinstance(x, dict):
                for v in x.values():
                    _gez(v)
            elif isinstance(x, list):
                for v in x:
                    _gez(v)
        _gez(j)
        kosulsuz = [m for m in metinler
                    if 'this result is a verification.' in m]
        assert not kosulsuz, f'koşulsuz doğrulama cümlesi: {kosulsuz}'
        assert any('No acceptance is issued' in m for m in metinler)

    def test_sayilar_ve_kapsam_alanlari_dokunulmadi(self, istemci):
        """Beyan düzeltmesi SAYIYA dokunmaz (regresyon kapısı)."""
        j = self._yanit(istemci, 45.0)
        sa = j['structural_analysis']['safety_analysis']
        assert sa['minimum_safety_factor'] == pytest.approx(4.0)
        assert sa['minimum_earned_safety_factor'] > sa['minimum_safety_factor']
        assert j['design_basis']['is_verification_scope'] == (
            'chamber wall thickness')
