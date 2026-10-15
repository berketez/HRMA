# -*- coding: utf-8 -*-
"""ÖH Dalga-32 · app-api-uc · aşama 2/2 — bekçiler.

Kalemler
--------
P7B4-23 (D31 DEVİR) + OH-D31-12 (hüküm-20 ayağı) — ``/api/validation/
upload-csv`` satır sınırı taşımıyordu. ÖLÇÜLDÜ (a2 ``once.json``, taban
``dd1dcddc``, bu makine): 600 000 satır HTTP **200**, 0,696 s, 8,42 MiB
yanıt; ne uçta ne ayrıştırıcıda satır bandı vardı. Tek sınır
``MAX_CONTENT_LENGTH`` (32 MiB) BAYT tavanıydı ve ölçülen 18,0 bayt/satır
ile ~1,86 milyon satıra denk düşüyordu (K3).

Başlığın "10,3 MiB yanıt üretiyor" (istekten BÜYÜK yanıt) yarısı D31'de
çürütülmüştü (kat 0,992) ve bu ölçümde de çürük (kat 0,742) — bu dosya o
yarıyı YENİDEN İDDİA ETMEZ.

Onarım: kanonik bant ``parse_thrust_csv``ın YANINDA
(``hrma/validation/user_data_validation.py``) tek kez tanımlanır, uç onu
OKUR. Aşım sessizce kırpılmaz; hangi sınırın hangi değerle aşıldığı
makine-okur biçimde döner (413).

OH-D31-04 — soğutma kanalı menüsü (radial ⟷ spiral). ÖLÇÜLDÜ
(``once_ohd3104.json``): iki koşu 37 374 ortak yaprağın 37 356'sında
birebir aynı; ayrışan 18 yaprağın 18'i de kullanıcının KELİMESİNİN echo'su
(``requested`` / ``params.geometry`` / ``indistinguishable_from``), FİZİK
yaprağı farkı **0**. Onarım panelin sahasındadır (``advanced.html`` menüsü
+ ``i18n_advanced.js`` etiketleri) ve o iki dosyaya bu dalgada KARDEŞ DAL
(``dalga32/arayuz-panel``) dokunduğu için bu kulvar DOKUNMADI. Buradaki
bekçi yalnız UÇ AYAĞINI kilitler: panelin okuyacağı alan üründe hazırdır ve
eşdeğerlik listesi ELLE YAZILMAZ, eşleme tablosundan türer.
"""
import ast
import io
import json
import os

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from hrma.app import app  # noqa: E402
from hrma.validation.user_data_validation import (  # noqa: E402
    THRUST_CSV_MIN_ROWS, THRUST_CSV_MAX_ROWS, THRUST_CSV_ROW_BAND,
    THRUST_CSV_HEADER_SEARCH_LINES, THRUST_CSV_MAX_NON_DATA_LINES,
    candidate_data_rows, thrust_csv_row_band_error, parse_thrust_csv,
    curve_point_count, compare as compare_thrust_curves,
)


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    return app.test_client()


def _kaynak(*parcalar):
    return io.open(os.path.join(KOK, *parcalar), encoding='utf-8').read()


def _atamalar(metin):
    """Modül düzeyindeki atama ADLARI (yorum METNİ sayılmaz)."""
    adlar = []
    for dugum in ast.walk(ast.parse(metin)):
        if isinstance(dugum, ast.Assign):
            for hedef in dugum.targets:
                if isinstance(hedef, ast.Name):
                    adlar.append(hedef.id)
        elif isinstance(dugum, ast.AnnAssign) and isinstance(
                dugum.target, ast.Name):
            adlar.append(dugum.target.id)
    return adlar


def _csv(satir, basliksiz=False, dt=0.001):
    govde = [] if basliksiz else ['time,thrust']
    govde += ['%.6f,%.3f' % (i * dt, 1000.0 + (i % 97)) for i in range(satir)]
    return '\n'.join(govde) + '\n'


# ===========================================================================
# P7B4-23 + OH-D31-12 — KANONİK SATIR BANDI
# ===========================================================================
class TestP7B423KanonikSatirBandi:
    """Bant VAR, ayrıştırıcının yanında, TEK kaynak ve uç onu okuyor."""

    def test_bant_ayristiricinin_yaninda_tanimli(self):
        adlar = _atamalar(
            _kaynak('hrma', 'validation', 'user_data_validation.py'))
        for ad in ('THRUST_CSV_MIN_ROWS', 'THRUST_CSV_MAX_ROWS',
                   'THRUST_CSV_ROW_BAND'):
            assert ad in adlar, (
                '%s ``parse_thrust_csv``ın yanında tanımlı değil — '
                'P7B4-23/OH-D31-12 gerilemiş' % ad)
        assert THRUST_CSV_ROW_BAND == (THRUST_CSV_MIN_ROWS,
                                       THRUST_CSV_MAX_ROWS)
        assert THRUST_CSV_MIN_ROWS >= 2 and THRUST_CSV_MAX_ROWS > 1000

    def test_ucta_IKINCI_tanim_yok_tek_kaynak(self):
        """Doktrin 4: sayı uçta yeniden yazılmaz, ithal edilir."""
        adlar = _atamalar(_kaynak('hrma', 'app.py'))
        ikizler = [a for a in adlar
                   if 'CSV' in a.upper() and 'ROW' in a.upper()]
        assert ikizler == [], (
            'satır bandı app.py içinde İKİNCİ kez tanımlanmış: %r' % ikizler)

    def test_uc_bandi_OKUYOR(self):
        """Uç gövdesi bant kapısını çağırıyor (iki kapı da aynı kaynak)."""
        metin = _kaynak('hrma', 'app.py')
        i = metin.index('def validation_upload_csv():')
        govde = metin[i:metin.index('@app.route', i + 10)]
        # CSV ekseninin İKİ kapısı (ayrıştırma öncesi + kesin sayım).
        # Üçüncü kapı ``predicted_curve`` ekseninindir, kendi sınıfında
        # ölçülür — bu iddia onu SAYMAZ.
        assert govde.count('_csv_satir_bandi_hatasi(_csv_aday_satir(') == 1
        assert govde.count("_csv_satir_bandi_hatasi(parsed['n_points'])") == 1

    def test_baslik_penceresi_de_tek_kaynak(self):
        """Başlık araması sabit sayı değil, bandın yanındaki adı okur."""
        metin = _kaynak('hrma', 'validation', 'user_data_validation.py')
        i = metin.index('# --- Başlık arama')
        j = metin.index('for idx in range(', i)
        kesit = metin[i:metin.index(':\n', j)]
        assert 'THRUST_CSV_HEADER_SEARCH_LINES' in kesit, kesit[-200:]
        assert 'range(min(5,' not in kesit
        assert 'ilk 5 satır' not in kesit
        assert THRUST_CSV_MAX_NON_DATA_LINES == (
            THRUST_CSV_HEADER_SEARCH_LINES + 1)


class TestP7B423UcDavranisi:
    """Bandın içi geçer, dışı SESSİZCE KIRPILMADAN reddedilir."""

    def _gonder(self, istemci, govde):
        return istemci.post('/api/validation/upload-csv',
                            data=govde.encode('utf-8'),
                            content_type='text/csv')

    def test_bandin_tam_tavani_KABUL(self, istemci):
        r = self._gonder(istemci, _csv(THRUST_CSV_MAX_ROWS))
        assert r.status_code == 200, (r.get_json() or {}).get('error')
        assert r.get_json()['parsed']['n_points'] == THRUST_CSV_MAX_ROWS

    def test_bandin_bir_ustu_REDDEDILIR(self, istemci):
        r = self._gonder(istemci, _csv(THRUST_CSV_MAX_ROWS + 1))
        assert r.status_code == 413, (
            'bant aşıldı ama uç %s döndü — satır sınırı yeniden kalkmış'
            % r.status_code)
        g = r.get_json()
        assert g['reason'] == 'row_band_exceeded'
        assert g['field'] == 'csv_rows'
        assert g['maximum'] == THRUST_CSV_MAX_ROWS
        assert g['minimum'] == THRUST_CSV_MIN_ROWS
        assert g['requested'] == THRUST_CSV_MAX_ROWS + 1
        assert str(THRUST_CSV_MAX_ROWS) in g['error']

    def test_asim_SESSIZCE_KIRPILMAZ(self, istemci):
        """Ret gövdesi kırpılmış bir seri taşımaz (doktrin 1)."""
        r = self._gonder(istemci, _csv(THRUST_CSV_MAX_ROWS + 1))
        g = r.get_json()
        assert 'parsed' not in g
        assert 'comparison' not in g
        assert g['status'] == 'error'

    def test_ret_bayt_tavanindan_DEGIL_satir_bandindan(self, istemci):
        """Kapı BAYT kapısı değil: reddedilen gövde 32 MiB'ın çok altında."""
        govde = _csv(THRUST_CSV_MAX_ROWS + 1)
        bayt = len(govde.encode('utf-8'))
        assert bayt < app.config['MAX_CONTENT_LENGTH'], (
            'ölçüm gövdeyi bayt tavanına çarptırıyor; satır ekseni '
            'ölçülemez')
        assert self._gonder(istemci, govde).status_code == 413

    def test_devasa_yuk_ayristirilmadan_kapanir(self, istemci):
        """Ayrıştırma ÖNCESİ kapı: 600 000 satır artık 200 DEĞİL."""
        r = self._gonder(istemci, _csv(600_000))
        assert r.status_code == 413
        g = r.get_json()
        assert g['requested'] > THRUST_CSV_MAX_ROWS
        # Yanıt artık isteğin yankısı değil, tek künyedir.
        assert len(r.get_data()) < 2000

    def test_bandin_altinda_400_ve_mesaj_banttan_geliyor(self, istemci):
        r = self._gonder(istemci, _csv(1))
        assert r.status_code == 400
        assert ('at least %d numeric' % THRUST_CSV_MIN_ROWS) in (
            r.get_json() or {}).get('error', '')

    def test_mesru_kucuk_dosya_etkilenmedi(self, istemci):
        r = self._gonder(istemci, 'time,thrust\n0,0\n1,100\n2,0\n')
        assert r.status_code == 200
        assert r.get_json()['parsed']['n_points'] == 3


class TestP7B423SayimSozlesmesi:
    """``candidate_data_rows`` ÜST sınırdır — banda sığan dosya kapanmaz."""

    def test_bos_satirlar_sayilmaz(self):
        assert candidate_data_rows(
            'time,thrust\n' + '\n' * 50 + '0,1\n1,2\n') == max(
                0, 3 - THRUST_CSV_MAX_NON_DATA_LINES)

    def test_ust_sinir_ozelligi(self):
        """Aday sayım >= gerçek n_points (bozuk satırlar ayıklanır)."""
        govde = ('time,thrust\n'
                 + ''.join('%d,%d\n' % (i, i) for i in range(20))
                 + 'bozuk;satir\nyine bozuk\n')
        aday = candidate_data_rows(govde)
        gercek = parse_thrust_csv(govde)['n_points']
        assert aday >= gercek - THRUST_CSV_MAX_NON_DATA_LINES
        assert gercek == 20

    def test_band_ici_hata_uretmez(self):
        assert thrust_csv_row_band_error(THRUST_CSV_MAX_ROWS) is None
        assert thrust_csv_row_band_error(0) is None
        assert thrust_csv_row_band_error('abc') is None

    def test_band_disi_kunyesi_makine_okur(self):
        k = thrust_csv_row_band_error(THRUST_CSV_MAX_ROWS + 7)
        assert k['limit'] == 'data_rows'
        assert k['requested'] == THRUST_CSV_MAX_ROWS + 7
        assert k['maximum'] == THRUST_CSV_MAX_ROWS


# ===========================================================================
# OH-D31-04 — soğutma kanalı menüsü: UÇ AYAĞI hazır (panel ayağı DEVİR)
# ===========================================================================
class TestOHD3104UcAyagi:
    """Panelin okuyacağı alan üründe DURUYOR ve liste ELLE YAZILMIYOR.

    Panel ayağı (menüyü birleştirme ya da 'aynı sonucu verir' etiketi)
    ``hrma/templates/advanced.html`` + ``hrma/static/js/i18n_advanced.js``
    sahasındadır; bu dalgada kardeş dal ``dalga32/arayuz-panel`` o iki
    dosyaya dokunduğu için bu kulvar DOKUNMADI (devir raporda).
    """

    def test_esdegerlik_listesi_eslemeden_TURUYOR(self):
        from hrma.engines.hybrid_rocket_engine import (
            COOLING_CHANNEL_TO_TYPE, COOLING_GEOMETRY_EQUIVALENCE)
        beklenen = {}
        for secim, sinif in COOLING_CHANNEL_TO_TYPE.items():
            if secim != sinif:
                beklenen.setdefault(sinif, []).append(secim)
        for sinif, secimler in beklenen.items():
            assert sorted(secimler) == sorted(
                COOLING_GEOMETRY_EQUIVALENCE.get(sinif, ())), (
                '%s sınıfının eşdeğerlik listesi eşlemeden türemiyor' % sinif)
        assert 'spiral' in COOLING_GEOMETRY_EQUIVALENCE['regenerative']
        assert 'radial' in COOLING_GEOMETRY_EQUIVALENCE['regenerative']

    def test_ucun_yayimladigi_alan_panele_hazir(self, istemci):
        """/calculate yanıtı motor bloğunda beyanı taşıyor (ölçüldü)."""
        r = istemci.post('/calculate', json={
            'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
            'chamber_pressure': 20, 'of_ratio': 6.0,
            'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
            'cooling_channels': 'radial'})
        assert r.status_code == 200, (r.get_json() or {}).get('error')
        motor = (r.get_json() or {}).get('motor') or {}
        blok = motor.get('cooling_channel_geometry')
        assert isinstance(blok, dict), (
            'cooling_channel_geometry kaybolmuş — OH-D31-04 panel onarımının '
            'okuyacağı kaynak yok')
        assert blok['requested'] == 'radial'
        assert blok['modelled'] is False
        assert blok['status'] == 'NOT_MODELLED'
        assert list(blok['indistinguishable_from']) == ['spiral']
        assert 'regenerative' in blok['equivalence_classes']


class TestP7B423PredictedCurveEkseni:
    """P7B4-23'ün JSON ayağı: ``predicted_curve`` dizisi de bantlı.

    ÖLÇÜLDÜ (``once_pc.json`` / ``sonra_pc.json``): CSV bandı geldikten
    SONRA bile bu eksen sınırsızdı — 300 000 noktalık tahmin eğrisi HTTP
    200 alıyor ve karşılaştırma hesaplanıyordu. Bant AYNI tek kaynaktan
    okunur; yalnız ret künyesinin ``field``ı ekseni adlandırır.
    """

    def _kucuk_csv(self):
        return ('time,thrust\n'
                + ''.join('%.3f,%.1f\n' % (i * 0.01, 1000.0)
                          for i in range(200)))

    def _egri(self, n):
        return {'time': [i * 0.00001 for i in range(n)],
                'thrust': [1000.0] * n}

    def _gonder(self, istemci, n):
        return istemci.post(
            '/api/validation/upload-csv',
            json={'csv_text': self._kucuk_csv(),
                  'predicted_curve': self._egri(n)})

    def test_bant_ici_tahmin_egrisi_KABUL(self, istemci):
        r = self._gonder(istemci, 500)
        assert r.status_code == 200, (r.get_json() or {}).get('error')
        assert r.get_json()['comparison'] is not None

    def test_bant_disi_tahmin_egrisi_413(self, istemci):
        r = self._gonder(istemci, THRUST_CSV_MAX_ROWS + 1)
        assert r.status_code == 413, (
            'predicted_curve ekseni yine sınırsız — %s' % r.status_code)
        g = r.get_json()
        assert g['field'] == 'predicted_curve', (
            'ret künyesi hangi eksenin aşıldığını söylemiyor: %r'
            % g.get('field'))
        assert g['reason'] == 'row_band_exceeded'
        assert g['maximum'] == THRUST_CSV_MAX_ROWS
        assert g['requested'] == THRUST_CSV_MAX_ROWS + 1
        assert 'comparison' not in g and 'parsed' not in g

    def test_uc_IKI_ekseni_de_ayni_kaynaktan_bantliyor(self):
        metin = _kaynak('hrma', 'app.py')
        i = metin.index('def validation_upload_csv():')
        govde = metin[i:metin.index('@app.route', i + 10)]
        assert govde.count('_csv_satir_bandi_hatasi(') == 3, (
            'uç üç kapıyı (csv ön, csv kesin, predicted_curve) aynı '
            'kaynaktan çağırmıyor')
        assert "field='predicted_curve'" in govde

    def test_sayim_diziyi_numpye_CEVIRMEDEN_olcuyor(self):
        """Bandı ölçerken korumak istediğimiz bellek harcanmaz."""
        import inspect
        kaynak = inspect.getsource(curve_point_count)
        assert 'asarray' not in kaynak and 'np.' not in kaynak

    def test_anahtar_cozumu_TEK_kaynak(self):
        """``curve_point_count`` ile ``_as_curve`` aynı çözümü okur."""
        from hrma.validation import user_data_validation as uv
        import inspect
        assert '_curve_parts(' in inspect.getsource(uv._as_curve)
        assert '_curve_parts(' in inspect.getsource(curve_point_count)
        # takma adlar da sayılıyor
        assert curve_point_count({'t': [0, 1, 2], 'F': [1, 2, 3]}) == 3
        assert curve_point_count([[0, 1], [5, 6]]) == 2
        assert curve_point_count({'bozuk': 1}) == 0
        assert curve_point_count(None) == 0

    def test_cozulemeyen_egri_bantta_DEGIL_400de_karsilanir(self, istemci):
        """Fail-closed korunur: bant 0 der, uç kendi 400'ünü verir."""
        r = istemci.post('/api/validation/upload-csv',
                         json={'csv_text': self._kucuk_csv(),
                               'predicted_curve': {'bozuk': [1, 2]}})
        assert r.status_code == 400
        assert (r.get_json() or {}).get('error')

    def test_kunye_alan_adi_varsayilani_bozulmadi(self):
        assert thrust_csv_row_band_error(
            THRUST_CSV_MAX_ROWS + 1)['field'] == 'csv_rows'

    def test_compare_bant_ici_egriyi_hala_hesapliyor(self):
        """Ortak helper çıkarımı ``compare``ı bozmadı."""
        n = 50
        egri = {'time': [i * 0.1 for i in range(n)],
                'thrust': [1000.0] * n}
        c = compare_thrust_curves(egri, egri)
        assert c['metrics']['nrmse_pct'] == 0.0
