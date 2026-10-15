# -*- coding: utf-8 -*-
"""ÖH D33 · ihracat a1 — OH-D27-11 (ŞART) · OH-D32-10 · OH-UC-10 bekçileri.

Kanıt: ``docs/scofield/raw/OH/D33/ihracat/a1/`` (``once.json`` / ``sonra.json``
/ ``mutasyon.json``, ölçüm betiği ``olcum.py``, izleyici ``izleyici.py``).
Taban ``56f88e70``.

OH-D27-11 (DENETİM ŞARTI — ihracat payı)
========================================
Şart: *"Dairesel zinciri tetikleyen modül-düzeyi ithali ADIYLA ölç (bekçinin
kendi alt-süreç sırasını çoğaltıp hangi ithalin ``hrma.engines``i yarım
bıraktığını sabitle). Tetikleyici ``hrma/export/*.py`` içindeki modül-düzeyi
``hrma.utils`` ithallerinden biriyse o ithal fonksiyon gövdesine taşınsın;
değilse ölçüm yazılı olarak beyan edilsin."*

ÖLÇÜLDÜ (``once.json`` K1, taban ağacı
``scratchpad/d33/taban``; ``izleyici.py``, ``sys.meta_path`` kancası —
``builtins.__import__`` sarmalı YETMEZ, paket ``__init__``lerinin
``importlib.import_module`` ile yaptığı yüklemeleri görmez ve ilk ölçümde
halkanın ağzı bu yüzden boş çıkmıştı):

    mevcut ağaç      : 0 uyarı · 8 ``hrma.engines.*`` modülü · 800 kenar
                       · ``hrma.engines`` YARIMKEN ``hrma.utils`` paketinin
                         İLK KEZ yüklendiği kenar: **0**
    eager yüzey (v2.6.26 davranışı, geçici mutasyon, md5 geri yazıldı):
                       1 uyarı · 4 modül · zincir ADIYLA:
                         ``hrma/utils/injector_design.py:30 -> hrma.engines``
                         ``hrma/engines/__init__.py:4 ->
                           hrma.engines.hybrid_rocket_engine``
                         ``hrma/engines/hybrid_rocket_engine.py:4 ->
                           hrma.utils.numeric_compat``  (engines YARIM)

YAZILI BEYAN: tetikleyici ``hrma/export/*.py`` DEĞİLDİR. Sahadaki sekiz
modül-düzeyi ``hrma.utils`` ithalinin (``cad_export`` 15, ``cad_visualization``
15, ``drawing_generator`` 29, ``motor_geometry`` 35, ``openrocket_integration``
10 ve 16, ``pdf_generator`` 14, ``pdf_safety`` 43, ``step_export`` 73) HİÇBİRİ
zincirde görünmez; hepsi YAPRAK alt-modül yolunu kullanır ve yaprak tek başına
0 ``hrma.engines`` / 0 ``hrma.analysis`` modülü çeker (``once.json``
``yaprak_tek_basina``). Zincirin ağzı ``hrma/utils/__init__`` yüzeyidir ve
D32 / OH-D31-06 ile çağrı anına geciktirilmiştir. Bu yüzden ihracat sahasında
TAŞINACAK bir ithal yoktur; şartın ikinci kolu (ölçümü adıyla beyan et)
uygulanır ve ölçüm aşağıda MANDALLANIR.

OH-D32-10
=========
ÖLÇÜLDÜ (``once.json`` K2): ``/calculate_solid`` gövdesi iki-faz düzeltme
durumunu İKİ yerde yayımlıyor (``not_applied_unverified``), ihracat ucu ise
teslim Isp'sini (243,68589734650317 s) 0 durum alanıyla aktarıyordu —
``export_motor_summary`` 0, ``.eng`` künyesi 0 satır, uçuş verisi 0 alan.
Hibrit / sıvıda çözücü hiç durum yayımlamıyor, ihracat yine Isp teslim
ediyordu (226,0777826151255 s / 259,79323443105085 s).

SONRA (``sonra.json`` K2): üç motorda da özet 4 alan, künye +2/+3 satır,
uçuş verisi 1 alan; Isp sayıları BİT-AYNI.

OH-UC-10
========
ÖLÇÜLDÜ (``once.json`` K3): ``mass could not be estimated`` cümlesi İKİ ayrı
f-string bloğunda (``ork_import.py`` 1079 kanat / 1117 dış bileşen), ortak
üretici YOK. Gerileme kilidi (P9B5-17 ``'Body'``) ve
``test_z5s_ice_aktarma_kapilari`` (``'Burun'``) yalnız DIŞ BİLEŞEN dalını
tutuyordu; kanat dalı bekçisizdi — ölçümle kanat dalının GERÇEKTEN ateşlediği
gösterildi (malzemesiz ve kalınlıksız kanat: 1'er uyarı).
SONRA: tanım noktası 2 → 1 (``_mass_not_estimated_warning``), ürün çıktısı
birebir aynı.
"""

import ast
import json
import os
import subprocess
import sys

import pytest
from tests.support.kanit import kanit_gerekli

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _KOK not in sys.path:
    sys.path.insert(0, _KOK)

_KANIT = os.path.join(_KOK, 'docs', 'scofield', 'raw', 'OH', 'D33',
                      'ihracat', 'a1')
_IZLEYICI = os.path.join(_KANIT, 'izleyici.py')

#: ``once.json`` K1 — mevcut ağaçta tam yüklenen motor modülü sayısı.
#: Yarım yükleme bu sayıyı 4'e düşürür (eager mutasyonuyla ölçüldü).
ENGINES_MODUL_TABANI = 8


def _ortam():
    return dict(os.environ, PYTHONPATH=_KOK, PYTHONDONTWRITEBYTECODE='1',
                HRMA_HEADLESS='1')


@pytest.fixture(scope='module')
def izleme():
    """Bekçinin (D30 OHD2906) alt-süreç sırası + kenar izleyicisi."""
    r = subprocess.run([sys.executable, '-W', 'always', kanit_gerekli(_IZLEYICI), _KOK],
                       capture_output=True, text=True, cwd=_KOK,
                       env=_ortam(), timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    satir = [s for s in r.stdout.splitlines() if s.startswith('{')]
    assert satir, r.stdout[-1000:]
    return json.loads(satir[-1])


# ===========================================================================
# OH-D27-11 (ŞART) — zincirin tetikleyicisi ADIYLA ölçülür ve mandallanır
# ===========================================================================
class TestOHD2711ZincirTetikleyicisi:
    """Şartın ölçüm ayağı: kim ``hrma.engines``i yarım bırakıyor?"""

    def test_engines_yarimken_utils_paketi_ILK_KEZ_yuklenmiyor(self, izleme):
        """Zincirin AĞZI kapalı — kapı kenarı sayısı 0.

        Kapı kenarı = ``hrma.engines`` ``_initializing`` iken ``hrma.utils``
        (paket ya da alt-modülü) İLK KEZ yüklenmesi. Eager yüzeyde bu kenar
        ``hrma/engines/hybrid_rocket_engine.py:4`` olarak ölçüldü ve motor
        paketi 8 modülden 4'e düştü.
        """
        kapi = izleme['kapi_kenarlari']
        assert kapi == [], (
            'hrma.engines yarimken hrma.utils ILK KEZ yukleniyor — dairesel '
            'tuzak yeniden kuruldu: '
            + '; '.join('%s:%s -> %s' % (k['dosya'], k['satir'], k['hedef'])
                        for k in kapi))

    def test_motor_paketi_TAM_yukleniyor_ve_uyari_yok(self, izleme):
        """Ürün ölçüsü: uyarı 0 ve modül sayısı taban değerinin altına inmez."""
        assert izleme['uyari_sayisi'] == 0, (
            'hrma.engines eksik yuklendi (uyari %s)'
            % izleme['uyari_sayisi'])
        assert izleme['engines_modul_sayisi'] >= ENGINES_MODUL_TABANI, (
            'motor paketi yarim yuklendi: %s modul (taban %s)'
            % (izleme['engines_modul_sayisi'], ENGINES_MODUL_TABANI))

    def test_ihracat_sahasi_zincirin_ICINDE_DEGIL(self, izleme):
        """YAZILI BEYANIN mandalı: zincirde hiçbir ``hrma/export`` kenarı yok.

        Şartın birinci kolu (tetikleyici ihracat sahasındaysa ithali gövdeye
        taşı) ÖLÇÜMLE düşer; ikinci kol (beyan et) uygulanır. Bu bekçi beyanı
        ölçüye bağlar: ihracat sahası zincire girerse kırmızı olur.
        """
        ihlal = [k for k in izleme['kapi_kenarlari']
                 + izleme['geri_giren_kenarlar']
                 + izleme['utils_init_icinden_cikan_kenarlar']
                 if (k.get('dosya') or '').startswith('hrma/export/')]
        assert ihlal == [], (
            'ihracat sahasi dairesel zincire girdi: '
            + '; '.join('%s:%s -> %s' % (k['dosya'], k['satir'], k['hedef'])
                        for k in ihlal))

    def test_saha_ithalleri_YAPRAK_alt_modul_yolunu_kullanir(self):
        """``hrma/export/*.py`` modül düzeyinde paket YÜZEYİNİ istemez.

        ``from hrma.utils import X`` paketin ``__init__``ini çalıştırıp adı
        yüzeyden çözdürür; ``from hrma.utils.<yaprak> import X`` yaprağı
        doğrudan ister. D32'de yüzey gecikmeli hâle geldi, ama sahanın
        sözleşmesi yazılı DEĞİLDİ — burada yazılı.
        """
        dizin = os.path.join(_KOK, 'hrma', 'export')
        paket_yuzeyi = []
        yaprak = []
        for ad in sorted(os.listdir(dizin)):
            if not ad.endswith('.py'):
                continue
            agac = ast.parse(open(os.path.join(dizin, ad),
                                  encoding='utf-8').read())
            for dugum in agac.body:          # YALNIZ modul duzeyi
                if not isinstance(dugum, ast.ImportFrom):
                    continue
                hedef = dugum.module or ''
                if hedef == 'hrma.utils':
                    paket_yuzeyi.append('hrma/export/%s:%d' % (ad,
                                                               dugum.lineno))
                elif hedef.startswith('hrma.utils.'):
                    yaprak.append('hrma/export/%s:%d' % (ad, dugum.lineno))
        assert paket_yuzeyi == [], (
            'ihracat sahasi modul duzeyinde paket yuzeyini istiyor: %s'
            % paket_yuzeyi)
        assert len(yaprak) >= 8, (
            'olculen sekiz yaprak ithali bulunamadi: %s' % yaprak)


# ===========================================================================
# OH-D32-10 — teslim Isp'si iki-faz düzeltme DURUMUNU taşır
# ===========================================================================
from hrma.export.openrocket_integration import (      # noqa: E402
    TWO_PHASE_BASIS_FIELD, TWO_PHASE_STATE_PATHS,
    TWO_PHASE_STATUS_FIELD, TWO_PHASE_STATUS_NOT_PUBLISHED,
    TWO_PHASE_VERIFIED_FIELD, OpenRocketExporter,
)


class TestOHD3210DurumBeyaniIhracatYuzeyinde:

    @pytest.fixture(scope='class')
    def ihracatci(self):
        return OpenRocketExporter()

    def test_cozucunun_yayimladigi_durum_HER_yoldan_okunur(self, ihracatci):
        """Beş arama yolunun her biri çözücünün durumunu getirir."""
        for yol in TWO_PHASE_STATE_PATHS:
            govde = {TWO_PHASE_STATUS_FIELD: 'not_applied_unverified',
                     TWO_PHASE_VERIFIED_FIELD: False,
                     TWO_PHASE_BASIS_FIELD: 'kunye metni'}
            veri = govde
            for anahtar in reversed(yol):
                veri = {anahtar: veri}
            durum = ihracatci.resolve_two_phase_correction(veri)
            assert durum[TWO_PHASE_STATUS_FIELD] == 'not_applied_unverified'
            assert durum['two_phase_correction_source'] == '.'.join(yol)

    def test_durum_yoksa_FAIL_CLOSED_beyan(self, ihracatci):
        """Sessiz "duzeltilmis" varsayimi YOK: eksiklik adiyla yazilir."""
        durum = ihracatci.resolve_two_phase_correction({})
        assert durum[TWO_PHASE_STATUS_FIELD] == TWO_PHASE_STATUS_NOT_PUBLISHED
        assert durum[TWO_PHASE_VERIFIED_FIELD] is False
        kunye = durum[TWO_PHASE_BASIS_FIELD]
        for yol in TWO_PHASE_STATE_PATHS:
            assert '.'.join(yol) in kunye, (
                'aranan yol kunyede adiyla yok: %s' % '.'.join(yol))

    def test_dogrulanmis_YALNIZ_cozucu_True_derse(self, ihracatci):
        """"bilinmiyor" bir dogrulama degildir."""
        for deger, beklenen in ((True, True), (False, False), (None, False),
                                ('true', False), (1, False)):
            veri = {'two_phase_loss': {
                TWO_PHASE_STATUS_FIELD: 'not_required_zero_condensed_phase',
                TWO_PHASE_VERIFIED_FIELD: deger}}
            durum = ihracatci.resolve_two_phase_correction(veri)
            assert durum[TWO_PHASE_VERIFIED_FIELD] is beklenen, deger

    def test_ozet_ve_ucus_verisi_AYNI_durumu_tasir(self, ihracatci):
        """Tek cozucu: motor ozeti ile ucus verisi ayrismaz."""
        veri = {'two_phase_loss': {
            TWO_PHASE_STATUS_FIELD: 'not_applied_unverified',
            TWO_PHASE_VERIFIED_FIELD: False,
            TWO_PHASE_BASIS_FIELD: 'kunye'}}
        ozet = ihracatci.export_motor_summary(veri)
        ucus = ihracatci.create_flight_simulation_data(veri)
        assert ozet[TWO_PHASE_STATUS_FIELD] == 'not_applied_unverified'
        assert (ucus['two_phase_correction'][TWO_PHASE_STATUS_FIELD]
                == ozet[TWO_PHASE_STATUS_FIELD])

    def test_durum_dizeleri_ihracatta_YENIDEN_yazilmaz(self):
        """TEK KAYNAK: cozucunun bes durum sabiti burada kopyalanmaz."""
        from hrma.engines import solid_rocket_engine as kati
        metin = open(os.path.join(_KOK, 'hrma', 'export',
                                  'openrocket_integration.py'),
                     encoding='utf-8').read()
        # Kod govdesi (aciklama satirlari haric) durum dizesini icermemeli.
        kod = '\n'.join(s for s in metin.splitlines()
                        if not s.lstrip().startswith('#'))
        for ad in ('TWO_PHASE_STATUS_NOT_APPLIED', 'TWO_PHASE_STATUS_USER',
                   'TWO_PHASE_STATUS_ZERO', 'TWO_PHASE_STATUS_NO_FRACTION',
                   'TWO_PHASE_STATUS_OUT_OF_ENVELOPE'):
            deger = getattr(kati, ad)
            assert deger not in kod, (
                'cozucunun durum dizesi ihracatta yeniden yazilmis: %s = %r'
                % (ad, deger))


class TestOHD3210UrunYolu:
    """Gercek cozucu sonucuyla uctan uca: /calculate_solid."""

    @pytest.fixture(scope='class')
    def kati_yanit(self):
        import contextlib
        import io
        import shutil
        import tempfile
        d = os.path.join(tempfile.gettempdir(), 'hrma-d33-ihracat-bekci')
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        os.environ['HRMA_USER_DATA_DIR'] = d
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                from hrma.app import app
                app.config['TESTING'] = True
                c = app.test_client()
                r = c.post('/calculate_solid', json={
                    'motor_name': 'D33-BEKCI', 'propellant_type': 'apcp',
                    'grain_type': 'bates', 'chamber_pressure': 40.0,
                    'thrust': 5000.0, 'burn_time': 3.0,
                    'chamber_diameter': 100.0, 'grain_length': 500.0,
                    'core_diameter': 30.0, 'expansion_ratio': 8.0})
        assert r.status_code == 200, r.status_code
        return r.get_json()

    def test_ihracat_durumu_COZUCUNUN_durumuyla_AYNI(self, kati_yanit):
        """Ayrisma yasak: ozet cozucunun kendi alanini tasir."""
        cozucu = kati_yanit['two_phase_loss'][TWO_PHASE_STATUS_FIELD]
        ozet = kati_yanit['openrocket']['motor_summary']
        assert ozet[TWO_PHASE_STATUS_FIELD] == cozucu, (
            'ihracat %r diyor, cozucu %r'
            % (ozet.get(TWO_PHASE_STATUS_FIELD), cozucu))
        assert ozet[TWO_PHASE_VERIFIED_FIELD] is False
        assert ozet['two_phase_correction_source'] in [
            '.'.join(y) for y in TWO_PHASE_STATE_PATHS]

    def test_teslim_isp_ile_durum_AYNI_sozlukte(self, kati_yanit):
        """Isp'yi okuyan, durumu gormeden okuyamaz."""
        ozet = kati_yanit['openrocket']['motor_summary']
        assert ozet['specific_impulse'] is not None
        assert TWO_PHASE_STATUS_FIELD in ozet

    def test_eng_kunyesi_durumu_YAZILI_tasir(self, kati_yanit):
        """RASP dosyasinin kendisi de hukmu tasir (yalniz API degil)."""
        eng = kati_yanit['openrocket']['eng_file']
        kunye = [s for s in eng.splitlines() if s.startswith(';')]
        iki_faz = [s for s in kunye if 'two-phase' in s.lower()]
        assert iki_faz, 'eng kunyesinde iki-faz durum satiri yok'
        assert any(kati_yanit['two_phase_loss'][TWO_PHASE_STATUS_FIELD] in s
                   for s in iki_faz), iki_faz


# ===========================================================================
# OH-UC-10 — iki dal TEK cümleden beslenir ve İKİSİ DE mandallı
# ===========================================================================
_MAT_GOVDE = '<material type="bulk" density="1200.0">PLA</material>'
_MAT_KANAT = '<material type="bulk" density="1400.0">G10</material>'
_KALINLIK = '<thickness>0.003</thickness>'

_ORK = """<?xml version="1.0"?><openrocket><rocket><name>T</name>
<subcomponents><stage><name>S</name><subcomponents>
<nosecone><name>Nose</name><length>0.15</length><aftradius>0.03</aftradius>
<thickness>0.002</thickness>%(BM)s</nosecone>
<bodytube><name>Body</name><length>0.60</length><radius>0.03</radius>
<thickness>0.002</thickness>%(BM)s
<subcomponents><trapezoidfinset><name>Fins</name><fincount>3</fincount>
<rootchord>0.20</rootchord><tipchord>0.10</tipchord><height>0.08</height>
<sweeplength>0.05</sweeplength>%(FT)s%(FM)s</trapezoidfinset>
</subcomponents></bodytube>
</subcomponents></stage></subcomponents></rocket></openrocket>"""


def _ork_metni(govde_mat=_MAT_GOVDE, kanat_mat=_MAT_KANAT,
               kanat_kalinlik=_KALINLIK):
    return _ORK % {'BM': govde_mat, 'FM': kanat_mat, 'FT': kanat_kalinlik}


def _ayristir(**kw):
    from hrma.importers import ork_import
    r = ork_import.parse_ork(_ork_metni(**kw).encode('utf-8'))
    assert 'error' not in r, r
    return r


def _kutle_uyarilari(r):
    return [u for u in r['warnings'] if 'mass could not be estimated' in u]


class TestOHUC10KutleBoslugu:

    def test_saglam_dosyada_UYARI_YOK_ve_uc_bilesen_var(self):
        r = _ayristir()
        assert _kutle_uyarilari(r) == []
        assert {'Nose', 'Body', 'Fins'} <= {c['name']
                                            for c in r['components']}

    def test_KANAT_dali_kutle_boslugunu_ADIYLA_bildirir(self):
        """P9B5-17 kilidinin TUTMADIGI dal (olculen bosluk, OH-UC-10)."""
        r = _ayristir(kanat_mat='')
        uyari = _kutle_uyarilari(r)
        assert len(uyari) == 1, uyari
        assert "trapezoidfinset 'Fins'" in uyari[0], uyari
        assert 'no bulk material density in file' in uyari[0], uyari
        assert 'Fins' not in {c['name'] for c in r['components']}

    def test_KANAT_dali_kalinlik_eksiginde_de_bildirir(self):
        """Ikinci ret gerekcesi de ADIYLA gecer (yoğunluk degil, kalinlik)."""
        r = _ayristir(kanat_kalinlik='')
        uyari = _kutle_uyarilari(r)
        assert len(uyari) == 1, uyari
        assert 'fin area/count/thickness missing in file' in uyari[0], uyari

    def test_DIS_BILESEN_dali_bildirmeye_devam_ediyor(self):
        """P9B5-17 gerileme kilidinin tuttugu dal — kirilmadi."""
        r = _ayristir(govde_mat='')
        uyari = _kutle_uyarilari(r)
        assert len(uyari) == 2, uyari
        assert any("bodytube 'Body'" in u for u in uyari), uyari
        assert any("nosecone 'Nose'" in u for u in uyari), uyari

    def test_IKI_dal_TEK_uretici_fonksiyondan_besleniyor(self):
        """Cumle iki yerde YAZILMAZ: tanim noktasi tam olarak 1."""
        yol = os.path.join(_KOK, 'hrma', 'importers', 'ork_import.py')
        metin = open(yol, encoding='utf-8').read()
        satirlar = [i + 1 for i, s in enumerate(metin.splitlines())
                    if 'mass could not be estimated' in s]
        assert len(satirlar) == 1, (
            'cumle %d yerde yaziliyor (once: 2, sonra: 1): %s'
            % (len(satirlar), satirlar))
        from hrma.importers import ork_import
        assert hasattr(ork_import, '_mass_not_estimated_warning')

    def test_IKI_dalin_cumlesi_uretici_ciktisiyla_BIREBIR_ayni(self):
        """Her iki dal da ureticinin dondurdugu dizeyi aynen yayimlar."""
        from hrma.importers.ork_import import _mass_not_estimated_warning
        kanat = _kutle_uyarilari(_ayristir(kanat_mat=''))[0]
        govde = [u for u in _kutle_uyarilari(_ayristir(govde_mat=''))
                 if "'Body'" in u][0]
        gerekce = ('no bulk material density in file; mass not estimated '
                   '(no fabricated defaults)')
        assert kanat == _mass_not_estimated_warning(
            'trapezoidfinset', 'Fins', gerekce)
        assert govde == _mass_not_estimated_warning(
            'bodytube', 'Body', gerekce)


def test_kanit_dosyalari_yerinde():
    for ad in ('olcum.py', 'izleyici.py', 'capa_kosumu.py', 'once.json',
               'sonra.json', 'mutasyon.json', 'rapor.md'):
        assert os.path.exists(kanit_gerekli(os.path.join(_KANIT, ad))), ad
