"""Z5S/P0 — içe aktarma ayrıştırıcılarının fizik kapıları (bekçi).

Kapsanan defter kalemleri (hepsi ÖNCE-ölçümüyle doğrulanmıştır; ölçüm
betiği ve önce/sonra çıktıları ``docs/scofield/raw/OH/Z5/p0/``):

- **P16B4-03** ``.ork`` negatif ``<length>`` → gövde kütlesi -0,379 kg,
  toplam 0,939 → 0,182 kg (%80,7 düşük), ``warnings`` boş, bileşen yine
  ``mapping_report.mapped`` içinde.
- **P16B4-04** ``.ork`` ``NaN`` uzunluk → 1,2 m'lik tüp sessizce 0 m,
  roket boyu 1,5 → 0,3 m, kanat konumu 1,3 → 0,1 m, uyarı yok.
- **P16B4-05** ``.ork`` negatif yoğunluk → bileşen kütle listesinden
  düşüyor ve aynı bileşen ``mapping_report``'un HEM ``mapped`` HEM
  ``skipped`` listesinde görünüyor (iç çelişki); üstelik ret gerekçesi
  "dosyada yoğunluk yok" diyerek YANLIŞ alanı suçluyor.
- **P16B4-13** ``.eng`` negatif zaman → toplam impuls 190 yerine 205 N·s
  (%7,9 fazla), örtük ateşleme noktası kuralı da devre dışı kalıyor.
- **P16B4-14** ``.eng`` başlığı metre yazılmış milimetre alanları (0,054 →
  "54 mikron çaplı motor") ve 1e12 N tepe itki uyarısız kabul ediliyor.
- **P16B4-28** ``.eng`` tek noktalı eğri "kullanılabilir motor" sayılıyor
  (örtük (0,0) noktası nokta sayısını ikiye çıkarıyor).

Sözleşme kimliği: ayrıştırıcılar istisna FIRLATMAZ, ``{"error",
"error_code"}`` döner; uç bunu 400 + ``error_code`` olarak iletir. Uyarı
yolunda hiçbir sayı DEĞİŞTİRİLMEZ (mm/m dönüşümü kendiliğinden yapılmaz),
yalnız adıyla bildirilir — uydurma-veri yasağı.

Bu dosya ``hrma/app.py``'ye dokunmaz: uçlar ``importers_api``
blueprint'inin kendi geçici Flask uygulamasında koşturulur (mevcut
``test_importers_*.py`` deseni).
"""

import base64
import re
from pathlib import Path

import pytest
from flask import Flask

from hrma.importers import motor_file, ork_import
from hrma.importers.api import importers_api

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'importers'

# Sağlıklı taban çıktısı (onarım öncesi ölçülen değerlerle BİT-AYNI).
# Kapılar sağlıklı yolu değiştirmemelidir.
SAGLIKLI_TOPLAM_KUTLE_KG = 0.9392481776006604
SAGLIKLI_BODY_LENGTH_M = 1.5
SAGLIKLI_FIN_POSITION_M = 1.3
SAGLIKLI_ENG_IMPULSE_NS = 189.99999999999997

# Geçerli bir RASP başlığı (çap 54 mm, boy 400 mm — makulluk bandı içinde)
ENG_BASLIK = 'HRMA-N 54 400 0-6 0.500 1.200 HRMA'


def _ork_metni(name='hrma_basic.ork'):
    return (FIXTURES / name).read_text(encoding='utf-8')


def _ork(metin):
    return ork_import.parse_ork(metin.encode('utf-8'))


def _tirnakli_adlar(kayitlar):
    """mapping_report satırlarındaki 'Ad' alanlarını çıkar."""
    return {ad for kayit in kayitlar for ad in re.findall(r"'([^']+)'", kayit)}


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.register_blueprint(importers_api)
    with app.test_client() as test_client:
        yield test_client


def _ork_ucu(client, metin):
    kodlu = base64.b64encode(metin.encode('utf-8')).decode('ascii')
    return client.post('/api/import/ork',
                       json={'content_base64': kodlu, 'filename': 'x.ork'})


def _eng_ucu(client, metin):
    return client.post('/api/import/motor-file',
                       json={'content': metin, 'filename': 'x.eng'})


# ---------------------------------------------------------------------------
# P16B4-03 / P16B4-04 — .ork uzunluk kapısı
# ---------------------------------------------------------------------------
class TestOrkUzunlukKapisi:
    def test_negatif_uzunluk_reddediliyor_kod_ve_ad_ile(self):
        """ÖNCE: 200 + Govde kütlesi -0,378763 kg, warnings boş."""
        sonuc = _ork(_ork_metni().replace('<length>1.2</length>',
                                          '<length>-1.2</length>'))
        assert 'error' in sonuc, 'negatif uzunluk hâlâ kabul ediliyor'
        assert sonuc['error_code'] == 'unphysical_component_length'
        # Gerekçe hangi bileşeni ve hangi alanı suçladığını söylemeli
        assert 'Govde' in sonuc['error']
        assert '<length>' in sonuc['error']
        assert 'components' not in sonuc  # hiçbir kütle üretilmedi

    @pytest.mark.parametrize('ham', ['NaN', 'nan', 'inf', '-inf', 'auto',
                                     'bir buçuk'])
    def test_sonlu_olmayan_uzunluk_sessizce_sifirlanmiyor(self, ham):
        """ÖNCE: NaN → tüp 0 m, roket 1,5 → 0,3 m, uyarı YOK."""
        sonuc = _ork(_ork_metni().replace('<length>1.2</length>',
                                          f'<length>{ham}</length>'))
        assert 'error' in sonuc, f"'{ham}' hâlâ sessizce 0 m'ye düşüyor"
        assert sonuc['error_code'] == 'unphysical_component_length'
        assert ham[:20] in sonuc['error']

    def test_eksik_uzunluk_sifir_kabul_ediliyor_ama_bildiriliyor(self):
        """Alan hiç yoksa 0 m kabul edilir — ama sessiz kalmaz."""
        sonuc = _ork(_ork_metni().replace('<length>1.2</length>', ''))
        assert 'error' not in sonuc
        assert any('<length> is missing' in u and 'Govde' in u
                   for u in sonuc['warnings'])

    def test_uc_negatif_uzunlukta_400_ve_kod_donduruyor(self, client):
        """ÖNCE: POST /api/import/ork → 200, error yok."""
        yanit = _ork_ucu(client, _ork_metni().replace(
            '<length>1.2</length>', '<length>-1.2</length>'))
        assert yanit.status_code == 400
        govde = yanit.get_json()
        assert govde['status'] == 'error'
        assert govde['error_code'] == 'unphysical_component_length'

    def test_negatif_paket_boyu_reddediliyor(self):
        """masscomponent packedlength de aynı kapıdan geçer."""
        sonuc = _ork(_ork_metni().replace('<packedlength>0.1</packedlength>',
                                          '<packedlength>-0.1</packedlength>'))
        assert 'error' in sonuc
        assert sonuc['error_code'] == 'unphysical_component_length'


class TestOrkNegatifKutleYasagi:
    """Kütle bütçesine negatif/sonlu-olmayan bileşen GİRMEZ."""

    def test_negatif_beyan_edilmis_kutle_reddediliyor(self):
        sonuc = _ork(_ork_metni().replace('<mass>0.35</mass>',
                                          '<mass>-0.35</mass>'))
        assert 'error' in sonuc
        assert sonuc['error_code'] == 'unphysical_component_mass'
        assert 'Aviyonik' in sonuc['error']

    def test_sonlu_olmayan_kutle_gerekcesi_alani_dogru_suçluyor(self):
        """'no mass value' demek yanlış olurdu: alan VAR, sayı değil."""
        sonuc = _ork(_ork_metni().replace('<mass>0.35</mass>',
                                          '<mass>NaN</mass>'))
        assert 'error' not in sonuc
        assert any("'NaN' is not a finite number" in u and 'Aviyonik' in u
                   for u in sonuc['warnings'])

    @pytest.mark.parametrize('fixture', ['hrma_basic.ork', 'hrma_freeform.ork',
                                         'hrma_two_stage.ork'])
    def test_her_bilesen_kutlesi_sonlu_ve_pozitif(self, fixture):
        sonuc = _ork(_ork_metni(fixture))
        assert 'error' not in sonuc
        for bilesen in sonuc['components']:
            kutle = bilesen['mass_kg']
            assert kutle == kutle, f"{bilesen['name']} kütlesi NaN"
            assert kutle > 0, f"{bilesen['name']} kütlesi {kutle} kg"

    def test_negatif_kalinlik_kutle_uretmiyor(self):
        """Negatif kalınlık ince-kabuk hacmini negatife çevirebilirdi."""
        sonuc = _ork(_ork_metni().replace('<thickness>0.0015</thickness>',
                                          '<thickness>-0.0015</thickness>'))
        assert 'error' not in sonuc
        assert all(c['name'] != 'Govde' for c in sonuc['components'])
        assert any('Govde' in u and 'thickness' in u
                   for u in sonuc['warnings'])


# ---------------------------------------------------------------------------
# P16B4-05 — mapping_report iç tutarlılığı + dürüst gerekçe
# ---------------------------------------------------------------------------
class TestOrkEslemeRaporuTutarliligi:
    @pytest.fixture()
    def negatif_yogunluk(self):
        return _ork(_ork_metni().replace('density="1050.0"',
                                         'density="-1050.0"'))

    def test_ayni_bilesen_hem_mapped_hem_skipped_olamaz(self,
                                                        negatif_yogunluk):
        """ÖNCE: Burun hem mapped hem skipped listesindeydi."""
        rapor = negatif_yogunluk['mapping_report']
        ortak = _tirnakli_adlar(rapor['mapped']) & \
            _tirnakli_adlar(rapor['skipped'])
        assert not ortak, f'mapped/skipped çelişkisi: {sorted(ortak)}'
        assert 'Burun' in _tirnakli_adlar(rapor['mapped'])
        assert 'Burun' not in _tirnakli_adlar(rapor['skipped'])

    @pytest.mark.parametrize('fixture', ['hrma_basic.ork', 'hrma_freeform.ork',
                                         'hrma_two_stage.ork'])
    def test_tutarlilik_saglikli_dosyalarda_da_geçerli(self, fixture):
        rapor = _ork(_ork_metni(fixture))['mapping_report']
        ortak = _tirnakli_adlar(rapor['mapped']) & \
            _tirnakli_adlar(rapor['skipped'])
        assert not ortak, f'{fixture}: mapped/skipped çelişkisi {ortak}'

    def test_kutle_bosluğu_warnings_kanalindan_bildiriliyor(self,
                                                            negatif_yogunluk):
        """Düşen kütle sessiz kalmaz; bileşen adı + gerekçe yazılır."""
        uyarilar = [u for u in negatif_yogunluk['warnings'] if 'Burun' in u]
        assert uyarilar, 'kütle boşluğu hiçbir kanalda bildirilmiyor'
        assert any('mass could not be estimated' in u for u in uyarilar)

    def test_gerekce_negatif_yogunlugu_adiyla_soyluyor(self,
                                                       negatif_yogunluk):
        """ÖNCE: gerekçe 'dosyada yoğunluk yok' diyordu — dosyada VARDI."""
        metin = ' '.join(negatif_yogunluk['warnings'])
        assert 'density in file is -1050 kg/m3' in metin
        assert 'no bulk material density in file' not in metin

    def test_yogunluk_gercekten_yoksa_gerekce_onu_soyluyor(self):
        metin = _ork_metni().replace(
            '<material type="bulk" density="1050.0">Polistiren</material>', '')
        sonuc = _ork(metin)
        assert 'error' not in sonuc
        assert any('no bulk material density in file' in u and 'Burun' in u
                   for u in sonuc['warnings'])

    def test_mapping_report_anahtarlari_degismedi(self):
        rapor = _ork(_ork_metni())['mapping_report']
        assert set(rapor.keys()) == {'mapped', 'approximated', 'skipped'}


# ---------------------------------------------------------------------------
# P16B4-13 — negatif zaman
# ---------------------------------------------------------------------------
class TestNegatifZamanKapisi:
    NEGATIF = (f'{ENG_BASLIK}\n-0.1 100.0\n1.9 100.0\n2.0 0.0\n')
    SAGLIKLI = (f'{ENG_BASLIK}\n0.1 100.0\n1.9 100.0\n2.0 0.0\n')

    def test_eng_negatif_zaman_reddediliyor(self):
        """ÖNCE: 200 + total_impulse 205,0 N·s (gerçeği 190,0)."""
        sonuc = motor_file.parse_eng(self.NEGATIF)
        assert 'error' in sonuc, 'negatif zaman hâlâ kabul ediliyor'
        assert sonuc['error_code'] == 'negative_time'
        assert '-0.1' in sonuc['error']

    def test_saglikli_kardegi_hala_190_ns(self):
        sonuc = motor_file.parse_eng(self.SAGLIKLI)
        assert 'error' not in sonuc
        assert sonuc['computed']['total_impulse_ns'] == \
            pytest.approx(SAGLIKLI_ENG_IMPULSE_NS)

    def test_rse_negatif_zaman_da_reddediliyor(self):
        """Kapı ortak yolda (_finalize_motor) — iki biçim de korunur."""
        xml = ('<engine code="X" mfg="HRMA" dia="54" len="400"><data>'
               '<eng-data t="-0.1" f="10"/><eng-data t="1" f="10"/>'
               '<eng-data t="2" f="0"/></data></engine>')
        sonuc = motor_file.parse_rse(xml)
        assert 'error' in sonuc
        assert sonuc['error_code'] == 'no_usable_engine'
        assert 'Negative time' in sonuc['error']

    def test_uc_400_ve_kod_donduruyor(self, client):
        yanit = _eng_ucu(client, self.NEGATIF)
        assert yanit.status_code == 400
        assert yanit.get_json()['error_code'] == 'negative_time'

    def test_sifir_zaman_hala_geçerli(self):
        """Kapı t=0'ı kesmemeli (örtük ateşleme noktası tam olarak 0)."""
        sonuc = motor_file.parse_eng(f'{ENG_BASLIK}\n0.0 0.0\n1.0 50.0\n'
                                     '2.0 0.0\n')
        assert 'error' not in sonuc


# ---------------------------------------------------------------------------
# P16B4-14 — birim çelişkisi ve fizik-dışı büyüklük uyarıları
# ---------------------------------------------------------------------------
class TestMakullukUyarilari:
    def test_metre_yazilmis_baslik_birim_celiskisi_olarak_bildiriliyor(self):
        """ÖNCE: 0,054 mm (54 mikron) çap uyarısız kabul ediliyordu."""
        sonuc = motor_file.parse_eng(
            'HRMA-N 0.054 0.400 0-6 0.500 1.200 HRMA\n'
            '0.1 100.0\n1.9 100.0\n2.0 0.0\n')
        assert 'error' not in sonuc
        capi = [u for u in sonuc['warnings'] if 'diameter' in u]
        boyu = [u for u in sonuc['warnings'] if 'Header length' in u]
        assert capi and boyu, 'bant dışı ölçü hâlâ sessiz'
        assert 'METRES' in capi[0] and '54 mm' in capi[0]
        assert 'METRES' in boyu[0] and '400 mm' in boyu[0]

    def test_deger_degistirilmiyor_yalniz_bildiriliyor(self):
        """Uydurma düzeltme yasağı: mm/m dönüşümü KENDİLİĞİNDEN yapılmaz."""
        sonuc = motor_file.parse_eng(
            'HRMA-N 0.054 0.400 0-6 0.500 1.200 HRMA\n'
            '0.1 100.0\n1.9 100.0\n2.0 0.0\n')
        assert sonuc['meta']['diameter_mm'] == pytest.approx(0.054)
        assert sonuc['meta']['length_mm'] == pytest.approx(0.400)

    def test_fizik_disi_tepe_itki_bildiriliyor(self):
        """ÖNCE: 1e12 N (1 teranewton) uyarısız kabul ediliyordu."""
        sonuc = motor_file.parse_eng(f'{ENG_BASLIK}\n0.1 1e12\n1.9 1e12\n'
                                     '2.0 0.0\n')
        assert 'error' not in sonuc
        assert sonuc['computed']['peak_thrust_n'] == pytest.approx(1e12)
        assert any('above the plausible limit' in u
                   for u in sonuc['warnings'])

    def test_bant_disi_ust_sinir_da_bildiriliyor(self):
        sonuc = motor_file.parse_eng('HRMA-N 5000 400 0-6 0.5 1.2 HRMA\n'
                                     '0.1 100.0\n1.9 100.0\n2.0 0.0\n')
        assert any('outside the plausible range' in u and 'diameter' in u
                   for u in sonuc['warnings'])

    def test_saglikli_fixture_makulluk_uyarisi_uretmiyor(self):
        """Yanlış pozitif bekçisi: 54 mm x 400 mm motor bant içindedir."""
        sonuc = motor_file.parse_eng(
            (FIXTURES / 'hrma_single.eng').read_text(encoding='utf-8'))
        assert not any('plausible' in u for u in sonuc['warnings'])
        rse = motor_file.parse_rse(
            (FIXTURES / 'hrma_multi.rse').read_text(encoding='utf-8'))
        for motor in rse['motors']:
            assert not any('plausible' in u for u in motor['warnings'])

    def test_rse_baslik_olcusu_de_kapidan_geçiyor(self):
        xml = ('<engine code="X" mfg="HRMA" dia="0.054" len="0.4"><data>'
               '<eng-data t="0" f="0"/><eng-data t="1" f="10"/>'
               '<eng-data t="2" f="0"/></data></engine>')
        sonuc = motor_file.parse_rse(xml)
        assert 'error' not in sonuc
        assert any('METRES' in u for u in sonuc['motors'][0]['warnings'])


# ---------------------------------------------------------------------------
# P16B4-28 — tek noktalı eğri
# ---------------------------------------------------------------------------
class TestTekNoktaliEgri:
    def test_tek_nokta_kullanilabilir_motor_sayilmiyor(self):
        """ÖNCE: 200 + total_impulse 5,0 N·s, burn_time 0,095 s."""
        sonuc = motor_file.parse_eng(f'{ENG_BASLIK}\n0.1 100.0\n')
        assert 'error' in sonuc, 'tek noktalı eğri hâlâ motor sayılıyor'
        assert sonuc['error_code'] == 'single_point_curve'
        assert 'computed' not in sonuc

    def test_uc_400_donduruyor(self, client):
        yanit = _eng_ucu(client, f'{ENG_BASLIK}\n0.1 100.0\n')
        assert yanit.status_code == 400
        assert yanit.get_json()['error_code'] == 'single_point_curve'

    def test_iki_nokta_hala_kabul_ediliyor(self):
        """Kapı yalnız tek noktayı kesmeli (mevcut bekçi: son itki uyarısı)."""
        sonuc = motor_file.parse_eng(f'{ENG_BASLIK}\n0.1 50.0\n1.0 40.0\n')
        assert 'error' not in sonuc
        assert any('expected to end near 0 N' in u for u in sonuc['warnings'])


# ---------------------------------------------------------------------------
# Gerileme çapaları — kapılar sağlıklı yolu DEĞİŞTİRMEZ
# ---------------------------------------------------------------------------
class TestSaglikliYolBitAyni:
    def test_ork_kutle_ve_geometri_capalari(self):
        sonuc = _ork(_ork_metni())
        assert 'error' not in sonuc
        toplam = sum(c['mass_kg'] for c in sonuc['components'])
        assert toplam == pytest.approx(SAGLIKLI_TOPLAM_KUTLE_KG, rel=1e-12)
        assert sonuc['aero']['body_length'] == \
            pytest.approx(SAGLIKLI_BODY_LENGTH_M)
        assert sonuc['aero']['fin_position'] == \
            pytest.approx(SAGLIKLI_FIN_POSITION_M)
        assert sonuc['warnings'] == []

    def test_ork_ucu_hala_200(self, client):
        yanit = _ork_ucu(client, _ork_metni())
        assert yanit.status_code == 200
        assert yanit.get_json()['status'] == 'success'

    def test_eng_ucu_hala_200_ve_190_ns(self, client):
        yanit = _eng_ucu(client, (FIXTURES / 'hrma_single.eng')
                         .read_text(encoding='utf-8'))
        assert yanit.status_code == 200
        assert yanit.get_json()['motor']['computed']['total_impulse_ns'] == \
            pytest.approx(SAGLIKLI_ENG_IMPULSE_NS)

    def test_basarili_yanitta_error_code_alani_yok(self, client):
        """Kod yalnız hata sınıfı için vardır; başarıda uydurulmaz."""
        yanit = _ork_ucu(client, _ork_metni())
        assert 'error_code' not in yanit.get_json()
