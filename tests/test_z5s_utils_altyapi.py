"""Z5S / P10-Z5S-D — hrma.utils altyapı hijyeni bekçileri.

Kapsanan kalemler (Scofield ÖH defteri):
  P10B1-12  update_checker uzaktan gelen adı doğrudan yola koyuyordu
  P10B1-13  parse_version dört bileşenli sürümü üçe kırpıyordu
  P10B1-14  list_projects şemaya uymayan dosyayı sağlam gösteriyordu
  P10B1-19  job_runner'da iş başına zaman aşımı yoktu
  P10B1-23  yerel ayar yedeği ondalık ayracını virgüle çeviriyordu
  P10B1-24  hrma/utils/__init__.py içe aktarma hatasını yutuyordu
  P10B1-26  self_install._CMD_UNSAFE satır sonlarını geçiriyordu

Bekçi ilkesi: DAVRANIŞ ve KÜNYE kilitlenir, kesin ondalık ÇAPALANMAZ.
Testler ağa çıkmaz, kullanıcının gerçek dizinlerine yazmaz (tmp_path).
"""

import inspect
import json
import locale
import os
import re
import threading
import time

import pytest

from hrma.utils import input_guard as ig
from hrma.utils import job_runner as jr
from hrma.utils import projects as store
from hrma.utils import self_install as si
from hrma.utils import update_checker as uc


# =====================================================================
# P10B1-12 — indirilen dosya adının yol hijyeni
# =====================================================================

class TestIndirmeYolHijyeni:
    """Uzaktan gelen ad İki katmandan geçmeden dosya yoluna giremez."""

    def test_safe_join_gorece_kacisi_dizin_icinde_tutar(self, tmp_path):
        yol = ig.safe_join(str(tmp_path), '../../../Library/evil.dmg')
        assert ig.is_within_dir(str(tmp_path), yol)
        assert os.path.basename(yol) == 'evil.dmg'

    def test_safe_join_mutlak_yolu_yutmaz(self, tmp_path):
        # os.path.join'in tuzağı: ikinci bileşen mutlaksa birinciyi ATAR
        yol = ig.safe_join(str(tmp_path), '/etc/passwd')
        assert ig.is_within_dir(str(tmp_path), yol)

    def test_safe_join_sembolik_bag_kacisini_yakalar(self, tmp_path):
        """İKİNCİ katmanın gerekçesi: süzgeç temiz, yol yine de dışarı."""
        (tmp_path / 'kotu.dmg').symlink_to('/etc/passwd')
        with pytest.raises(ig.InputError):
            ig.safe_join(str(tmp_path), 'kotu.dmg')

    def test_is_within_dir_onek_tuzagina_dusmez(self, tmp_path):
        kok = tmp_path / 'x'
        kok.mkdir()
        komsu = tmp_path / 'xy'
        komsu.mkdir()
        assert ig.is_within_dir(str(kok), str(kok))
        assert ig.is_within_dir(str(kok), str(kok / 'a.txt'))
        assert not ig.is_within_dir(str(kok), str(komsu))

    def test_resolve_download_paths_indirilenler_disina_cikamaz(self, tmp_path):
        gecici, kesin = uc.resolve_download_paths(
            '../../../Library/evil.dmg', base=str(tmp_path))
        assert ig.is_within_dir(str(tmp_path), kesin)
        assert ig.is_within_dir(str(tmp_path), gecici)
        assert gecici.endswith('.download')

    def test_resolve_download_paths_mesru_adi_bozmaz(self, tmp_path):
        gecici, kesin = uc.resolve_download_paths(
            'HRMA-Kurulum-2.6.27-macOS.dmg', base=str(tmp_path))
        assert os.path.basename(kesin) == 'HRMA-Kurulum-2.6.27-macOS.dmg'
        assert os.path.basename(gecici) == (
            'HRMA-Kurulum-2.6.27-macOS.dmg.download')

    def test_update_checker_merkezi_suzgeci_kullaniyor(self):
        """Künye bekçisi: kendi ad süzgecini yazmak yerine input_guard."""
        kaynak = inspect.getsource(uc.resolve_download_paths)
        assert 'safe_join' in kaynak
        assert 'input_guard' in inspect.getsource(uc)

    def test_run_download_kotu_adda_indirmeye_baslamaz(self, monkeypatch,
                                                       tmp_path):
        """Fail-closed: ad çözülemezse ağ isteği HİÇ yapılmaz."""
        cagrildi = []

        def _patlayan_resolve(name, base=None):
            raise ig.InputError('ad guvenli yola cozulemedi')

        def _urlopen(*a, **k):
            cagrildi.append(a)
            raise AssertionError('ad reddedilmeliydi, ag istegi yapilmamali')

        monkeypatch.setattr(uc, 'resolve_download_paths', _patlayan_resolve)
        monkeypatch.setattr(uc.urllib.request, 'urlopen', _urlopen)
        uc._run_download('https://example.invalid/x.dmg', 'kotu', 0, '')
        durum = uc.download_status()
        assert cagrildi == []
        assert durum['state'] == 'error'
        assert 'unsafe installer file name' in durum['error']


# =====================================================================
# P10B1-13 — sürüm karşılaştırması dört bileşeni görür
# =====================================================================

class TestSurumKarsilastirmasi:
    def test_dort_bilesen_kirpilmiyor(self):
        assert uc.parse_version('v2.6.27.1') == (2, 6, 27, 1)
        assert uc.parse_version('v2.6.27.12') == (2, 6, 27, 12)

    def test_yama_surumu_yeni_sayilir(self):
        """Kalemin ta kendisi: 2.6.27 kullanıcısı 2.6.27.1'i görmüyordu."""
        assert uc.is_newer('v2.6.27.1', '2.6.27') is True
        assert uc.is_newer('v2.6.27', '2.6.27.1') is False

    def test_eksik_bilesen_sifir_sayilir(self):
        """(2,6,27) ile (2,6,27,0) AYNI sürümdür; demet boyu aldatmasın."""
        assert uc.is_newer('v2.6.27.0', '2.6.27') is False
        assert uc.is_newer('v2.6.27', '2.6.27.0') is False

    def test_uc_bilesen_sozlesmesi_korundu(self):
        # Eski bekçinin (test_update_checker.py) beklentisi bozulmadı
        assert uc.parse_version('2.3') == (2, 3, 0)
        assert uc.parse_version('') == (0, 0, 0)
        assert uc.parse_version(None) == (0, 0, 0)

    def test_on_surum_soneki_bilesen_sayilmaz(self):
        """'beta2'nin 2'si sürüm bileşeni değildir."""
        assert uc.parse_version('HRMA-2.4.0-beta2') == (2, 4, 0)
        assert uc.is_newer('HRMA-2.4.0-beta2', '2.4.0') is False

    def test_tarih_bicimli_etiket_hukmu_degismedi(self):
        """Ölçülen tek yan etki, HÜKÜM'ü değiştirmiyor.

        'release-2026-08-24' gibi tarih biçimli (sürüm olmayan) bir etiket
        eskiden (2026, 8, 24), şimdi (2026, 0, 0) veriyor: nokta ayraçlı
        çekirdek okunduğu için tireli parçalar bileşen sayılmıyor. İkisi de
        anlamlı bir sürüm değil; ÖNEMLİ olan verilen kararın aynı kalması.
        """
        assert uc.parse_version('release-2026-08-24') == (2026, 0, 0)
        assert uc.is_newer('release-2026-08-24', '2.6.27') is True  # HEAD de True


# =====================================================================
# P10B1-14 — liste ile yükleme aynı şema kapısını kullanır
# =====================================================================

@pytest.fixture
def proj_dir(tmp_path, monkeypatch):
    d = tmp_path / 'projects'
    d.mkdir()
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(d))
    return d


def _gecerli_yuk():
    """Şemaya uyan asgari proje yükü (test_projects_store ile aynı biçim)."""
    return {
        'format': 'hrma-project',
        'format_version': 1,
        'motor_type': 'hybrid',
        'inputs': {'fields': {'thrust': 1000.0, 'burn_time': 10}},
        'results_summary': {'isp': 245.3},
    }


class TestListelemeSemaKapisi:
    def test_semaya_uymayan_dosya_saglam_gorunmez(self, proj_dir):
        (proj_dir / 'semasiz.hrma').write_text(
            json.dumps({'bu': 'sema degil'}), encoding='utf-8')
        kayit = {p['name']: p for p in store.list_projects()}['semasiz']
        assert kayit['corrupt'] is True
        assert kayit['reason']

    def test_liste_ile_yukleme_ayni_gercegi_soyler(self, proj_dir):
        """Kalemin özü: listede açılabilir görünen dosya açılabilmelidir."""
        (proj_dir / 'semasiz.hrma').write_text(
            json.dumps({'bu': 'sema degil'}), encoding='utf-8')
        (proj_dir / 'saglam.hrma').write_text(
            json.dumps(dict(_gecerli_yuk(), name='saglam')), encoding='utf-8')
        for kayit in store.list_projects():
            acilabilir = True
            try:
                store.load_project(kayit['name'])
            except store.ProjectError:
                acilabilir = False
            assert acilabilir is (not kayit['corrupt']), (
                f"{kayit['name']}: liste corrupt={kayit['corrupt']} diyor ama "
                f"load_project acilabilir={acilabilir} diyor")

    def test_bozukluk_turu_ayirt_ediliyor(self, proj_dir):
        (proj_dir / 'json_degil.hrma').write_bytes(b'\x00\xffJSON degil{{{')
        (proj_dir / 'semasiz.hrma').write_text('{"bu": "sema degil"}',
                                               encoding='utf-8')
        kayitlar = {p['name']: p for p in store.list_projects()}
        assert kayitlar['json_degil']['reason_kind'] == 'unreadable'
        assert kayitlar['semasiz']['reason_kind'] == 'schema'

    def test_saglam_proje_hala_saglam(self, proj_dir):
        """Sağlıklı yol BİT-AYNI: geçerli proje listede bozuk görünmez."""
        store.save_project('normal', _gecerli_yuk())
        kayit = store.list_projects()[0]
        assert kayit['corrupt'] is False
        assert kayit['motor_type'] == 'hybrid'
        assert 'reason' not in kayit


# =====================================================================
# P10B1-19 — koşan işin süre sınırı BEYAN edilir (thread öldürülmez)
# =====================================================================

def _bekle(kosul, sure=5.0):
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.01)
    return False


class TestIsZamanAsimi:
    def test_takilan_is_sonlandirilmis_sayilir(self):
        kapi = threading.Event()
        r = jr.JobRunner(max_workers=1, ttl_seconds=60.0,
                         job_timeout_seconds=0.2)
        try:
            jid = r.submit(lambda: kapi.wait(30.0))
            assert _bekle(lambda: r.status(jid)['state'] == jr.STATE_ERROR)
            st = r.status(jid)
            assert st['timed_out'] is True
            assert 'time limit' in st['error']
        finally:
            kapi.set()

    def test_hata_metni_olduruldu_iddiasinda_bulunmaz(self):
        """Sahte iddia yasağı: CPython'da thread zorla öldürülemez."""
        kapi = threading.Event()
        r = jr.JobRunner(max_workers=1, ttl_seconds=60.0,
                         job_timeout_seconds=0.2)
        try:
            jid = r.submit(lambda: kapi.wait(30.0))
            assert _bekle(lambda: r.status(jid)['timed_out'])
            metin = r.status(jid)['error'].lower()
            # Doğru beyan: "terk edildi + hâlâ koşuyor olabilir".
            assert 'may still be running' in metin
            # Yasak beyan: işin öldürüldüğü/durdurulduğu iddiası.
            for yalan in ('was killed', 'has been killed', 'was terminated',
                          'has been terminated', 'was stopped', 'forced stop'):
                assert yalan not in metin, yalan
        finally:
            kapi.set()

    def test_takilan_is_kuyrugu_sonsuza_kadar_tikamiyor(self):
        """Kalemin ta kendisi: sonraki iş 'queued'de ölmez."""
        kapi = threading.Event()
        r = jr.JobRunner(max_workers=2, ttl_seconds=60.0,
                         job_timeout_seconds=0.2)
        try:
            r.submit(lambda: kapi.wait(30.0))
            r.submit(lambda: kapi.wait(30.0))
            assert _bekle(lambda: r.pending_count() == 0 or True, 0.3)
            sonraki = r.submit(lambda: 'gectim')
            assert _bekle(lambda: r.status(sonraki)['state'] == jr.STATE_DONE), \
                'takilan iki is sonraki isi hala tikiyor'
            assert r.status(sonraki)['result'] == 'gectim'
            assert r.abandoned_count() == 2
        finally:
            kapi.set()

    def test_terk_edilen_kayit_ttl_ile_temizlenir(self):
        """Eskiden finished_at None olduğu için TTL hiç işlemiyordu."""
        kapi = threading.Event()
        saat = {'t': 0.0}
        r = jr.JobRunner(max_workers=1, ttl_seconds=10.0,
                         job_timeout_seconds=0.2,
                         time_fn=lambda: saat['t'])
        try:
            jid = r.submit(lambda: kapi.wait(30.0))
            assert _bekle(lambda: r.status(jid)['state'] == jr.STATE_RUNNING)
            saat['t'] = 1.0           # sınırı aş
            assert r.status(jid)['timed_out'] is True
            saat['t'] = 100.0         # TTL'i de aş
            r.cleanup_expired()
            with pytest.raises(KeyError):
                r.status(jid)
        finally:
            kapi.set()

    def test_isbirlikci_is_zaman_asiminda_gercekten_durur(self):
        durdu = threading.Event()

        def uzun_is(cancel_event=None):
            for _ in range(2000):
                if cancel_event is not None and cancel_event.is_set():
                    durdu.set()
                    return 'iptal duyuldu'
                time.sleep(0.005)
            return 'hic durmadim'

        r = jr.JobRunner(max_workers=1, ttl_seconds=60.0,
                         job_timeout_seconds=0.2)
        jid = r.submit(uzun_is)
        assert _bekle(lambda: r.status(jid)['timed_out'])
        assert durdu.wait(5.0), 'zaman aşımı iptal olayını kaldırmadı'

    def test_gec_gelen_sonuc_bitmis_hukmu_degistirmez(self):
        kapi = threading.Event()
        r = jr.JobRunner(max_workers=1, ttl_seconds=60.0,
                         job_timeout_seconds=0.2)
        jid = r.submit(lambda: (kapi.wait(30.0), 'gec sonuc')[1])
        assert _bekle(lambda: r.status(jid)['timed_out'])
        kapi.set()
        time.sleep(0.3)
        st = r.status(jid)
        assert st['state'] == jr.STATE_ERROR      # 'done'a DÖNMEZ
        assert 'result' not in st
        # ...ama sonuç sessizce ÇÖPE de atılmaz: ayrı alanda beyan edilir
        assert st['late_result'] == 'gec sonuc'

    def test_zamaninda_biten_iste_gec_sonuc_alani_yok(self):
        r = jr.JobRunner(max_workers=1, ttl_seconds=60.0,
                         job_timeout_seconds=30.0)
        jid = r.submit(lambda: 'zamaninda')
        assert r.wait(jid, timeout=5.0)
        assert 'late_result' not in r.status(jid)

    def test_saglikli_is_zaman_asimindan_etkilenmez(self):
        """Dokunulmayan yol BİT-AYNI: normal iş aynı sonucu verir."""
        r = jr.JobRunner(max_workers=2, ttl_seconds=60.0,
                         job_timeout_seconds=30.0)
        idler = [r.submit(lambda i=i: i * i) for i in range(8)]
        for i, jid in enumerate(idler):
            assert r.wait(jid, timeout=5.0)
            st = r.status(jid)
            assert st['state'] == jr.STATE_DONE
            assert st['result'] == i * i
            assert st['timed_out'] is False

    def test_sinir_kapatilabilir(self):
        r = jr.JobRunner(max_workers=1, job_timeout_seconds=None)
        assert r._job_timeout is None
        jid = r.submit(lambda: 'ok')
        assert r.wait(jid, timeout=5.0)
        assert r.status(jid)['result'] == 'ok'

    def test_varsayilan_sinir_uydurma_degil_ttl_turevi(self):
        """Künye bekçisi: yeni eşik icat edilmedi, TTL'den türetildi."""
        assert jr.DEFAULT_JOB_TIMEOUT_SECONDS == jr.DEFAULT_TTL_SECONDS
        assert jr.JobRunner()._job_timeout == jr.DEFAULT_TTL_SECONDS

    def test_gecersiz_sinir_reddedilir(self):
        with pytest.raises(ValueError):
            jr.JobRunner(job_timeout_seconds=0)
        with pytest.raises(ValueError):
            jr.JobRunner(job_timeout_seconds=-1)


# =====================================================================
# P10B1-23 — yerel ayar yedeği ondalık ayracını virgüle çeviremez
# =====================================================================

class TestYerelAyarYedegi:
    def test_kullanicinin_yerel_ayarina_dusulmuyor(self):
        """setlocale(LC_ALL, '') tr/de Windows'ta ondalık ayracı VİRGÜL yapar."""
        from hrma.utils import windows_compatibility as wc
        kaynak = inspect.getsource(wc.WindowsCompatibility
                                   .setup_windows_environment)
        assert "locale.LC_ALL, ''" not in kaynak
        assert 'locale.LC_ALL, ""' not in kaynak

    def test_adaylarin_hepsi_nokta_ondalik(self):
        """Denenen her aday nokta ayraç vaat eder (bu makinede ölçülür)."""
        from hrma.utils import windows_compatibility as wc
        kaynak = inspect.getsource(wc.WindowsCompatibility
                                   .setup_windows_environment)
        adaylar = re.search(r"for _aday in \(([^)]*)\)", kaynak).group(1)
        adlar = [a.strip().strip("'\"") for a in adaylar.split(',') if a.strip()]
        assert adlar and adlar[-1] in ('C', 'C.UTF-8'), \
            'son yedek POSIX/C olmalı — kullanıcı yerel ayarı değil'
        onceki = locale.setlocale(locale.LC_ALL)
        try:
            for ad in adlar:
                try:
                    locale.setlocale(locale.LC_ALL, ad)
                except locale.Error:
                    continue          # bu makinede yok; iddia edilmez
                assert locale.localeconv()['decimal_point'] == '.', ad
        finally:
            locale.setlocale(locale.LC_ALL, onceki)

    def test_basarisizlik_beyan_ediliyor(self):
        """Hiçbir aday tutmazsa 'ayarladık' denmez."""
        from hrma.utils import windows_compatibility as wc
        kaynak = inspect.getsource(wc.WindowsCompatibility
                                   .setup_windows_environment)
        assert 'Locale NOT set' in kaynak


# =====================================================================
# P10B1-24 — paket yüzeyi yarım yüklenmiş hâlde sessiz kalmaz
# =====================================================================

class TestPaketYuzeyi:
    def test_ice_aktarma_hatasi_kayit_altinda(self):
        import hrma.utils as hu
        assert hasattr(hu, 'IMPORT_ERRORS')
        assert isinstance(hu.IMPORT_ERRORS, dict)

    def test_depo_bugun_tam_yukleniyor(self):
        import hrma.utils as hu
        # ÖH D32 / OH-D31-06: yüzey GECİKMELİ çözülüyor. Çağrısız
        # ``IMPORT_ERRORS`` boş olurdu ve iddia ÖLÇMEDEN geçerdi;
        # ``_load_exports()`` yüzeyin tamamını çözdürür (canlı yol).
        hu._load_exports()
        assert hu.IMPORT_ERRORS == {}, \
            f'paket yüzeyi eksik yüklendi: {hu.IMPORT_ERRORS}'
        # ÇEVRİLDİ — ÖH D30 / P10B1-05: ``of_optimizer`` ve
        # ``OptimumOFRatioFinder`` PAKET yüzeyinden çıkarıldı (ölü tablo
        # okuyucusu; ürün çağrısı 0, gerekçe hrma/utils/__init__.py'de).
        # Modül yolu (``hrma.utils.optimum_of_ratio``) korunur ve aşağıda
        # ayrıca sınanır — daralan yalnız paket özniteliği.
        for ad in ('validation', 'calculations', 'graph_fixes', 'fuel_mixer',
                   'export_fixes', 'InjectorDesign'):
            assert hasattr(hu, ad), f'dışa açılan ad kayboldu: {ad}'
        for ad in ('of_optimizer', 'OptimumOFRatioFinder'):
            assert not hasattr(hu, ad), f'ölü yol yüzeye geri geldi: {ad}'
        from hrma.utils.optimum_of_ratio import of_optimizer  # noqa: F401

    def test_eksik_ad_kullanilamaz_isaretli(self, monkeypatch):
        """Yutma yok: eksik ada dokunmak kök sebeple ImportError verir."""
        import hrma.utils as hu
        kok = ImportError('numpy: no module named numpy')
        monkeypatch.setitem(hu.IMPORT_ERRORS, 'InjectorDesign', kok)
        monkeypatch.delattr(hu, 'InjectorDesign')
        with pytest.raises(ImportError) as e:
            hu.InjectorDesign
        assert 'unavailable' in str(e.value)
        assert e.value.__cause__ is kok

    def test_bilinmeyen_ad_hala_attribute_error(self):
        import hrma.utils as hu
        with pytest.raises(AttributeError):
            hu.boyle_bir_ad_yok

    def test_her_modul_ayri_deneniyor(self):
        """Bir arıza öteki modülleri görünmez biçimde düşüremez.

        ÖH D30 / P10B1-05: burada ``len(hu._EXPORTS) == 3`` yazan bir SAYIM
        MANDALI duruyordu. Mandalın koruduğu şey sayı değil İLİŞKİdir —
        "her modül AYRI denenir" — ve ``optimum_of_ratio`` yüzeyden meşru
        biçimde çıkarılınca (ölü yol, ölçüm: ürün çağrısı 0) sayı bekçiyi
        sahte kırmızıya düşürüyordu. Mandal KÜME ölçüsüne çevrildi: liste
        MODÜL ADLARIYLA sınanır, sayı yükseltilmez/düşürülmez.
        """
        import hrma.utils as hu
        moduller = {m for m, _adlar in hu._EXPORTS}
        assert moduller == {'hrma.utils.common_fixes',
                            'hrma.utils.injector_design'}, moduller
        assert len(moduller) == len(hu._EXPORTS), \
            'aynı modül iki kez listelenmiş: yükleme sırası belirsizleşir'
        kaynak = inspect.getsource(hu._load_exports)
        assert 'continue' in kaynak


# =====================================================================
# P10B1-26 — batch kapısı satır sonlarını geçirmez
# =====================================================================

class TestBatchKapisi:
    @pytest.mark.parametrize('kotu', ['\n', '\r', '\t', '\x00', '\x1b'])
    def test_denetim_karakterleri_yakalanir(self, kotu):
        assert si._CMD_UNSAFE.search('C:\\Users\\a%sb\\HRMA' % kotu)

    def test_bilinen_cmd_karakterleri_hala_yakalaniyor(self):
        for ch in '&^%!<>|()"':
            assert si._CMD_UNSAFE.search('C:\\Users\\a%sb' % ch), ch

    def test_mesru_yollar_gecmeye_devam_ediyor(self):
        for iyi in ('C:\\Program Files\\HRMA',
                    'C:\\Users\\Berke Tezgocen\\AppData\\Local\\HRMA',
                    'C:\\HRMA-2.6.27'):
            assert not si._CMD_UNSAFE.search(iyi), iyi

    def test_satir_sonlu_yol_otomatik_moda_girmez(self, monkeypatch, tmp_path):
        """Kapı gerçekten plan kararına bağlı: auto DEĞİL, manual."""
        kurulum = tmp_path / 'HRMA-Setup.exe'
        kurulum.write_bytes(b'MZ')
        monkeypatch.setattr(si, 'find_win_install_dir',
                            lambda *a, **k: 'C:\\HRMA\nstart calc')
        monkeypatch.setattr(si, '_dir_writable', lambda *a, **k: True)
        plan = si.plan_install(str(kurulum), platform='win32',
                               installer_size=10)
        assert plan['mode'] == 'manual'
        assert 'unsafe for cmd' in plan['reason']
