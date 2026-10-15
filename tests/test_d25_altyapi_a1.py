"""ÖH D25 / altyapı a1 — KAPSAM KAPISI (defter P14H2-C1).

Kalemin iddiası iki parçalıydı:

1. *"Süit ``--cov`` altında **12 hayalet kırmızı** veriyor (kapsamsız 237
   passed / 0 kırmızı); hepsi grafik/PDF zaman aşımı + yedek çizici
   sınıfı."*
2. *"Sonuç: **bu depoya bugün kapsam kapısı kurulamaz** — kapı ilk gün 12
   kırmızıyla açılır."*

D24 aşama-2 birinci parçayı 43 testlik grafik/PDF kümesinde ölçtü (0
hayalet) ama ikinci parçayı **kaldıramadı**: tam süit ``--cov`` altında
bütçeye sığmadı (7 dk 40 sn'de ~52 test). D25 aşama-1 eksik ölçümü
tamamladı; ölçümün sonucu bu dosyanın koruduğu kapıdır.

ÖLÇÜLEN (5-6 Eylül 2026, bu depo, Python 3.12.7 + coverage 7.12; kanıt
``docs/scofield/raw/OH/D25/altyapi/a1/``):

* Kapsam çekirdeğinin maliyeti ÇEKİRDEĞE BAĞLI. Varsayılan C izleyici
  ``x1,54``-``x2,09`` yavaşlatıyor; ``COVERAGE_CORE=sysmon``
  (CPython 3.12 ``sys.monitoring``) ``x0,90``-``x1,04``, yani ölçüm
  gürültüsü içinde. D24'ün "süit kapsam altında bütçeye sığmıyor"
  gözlemi **çekirdek seçimiyle** düşüyor.
* Tam süit (487 dosya, 24 dilim, SIRALI, ``coverage combine``) sysmon
  çekirdeğiyle koşuldu ve kapsamsız taban koşumuna (taban kaydı-8, main
  ``cdf2106``) göre **hayalet kırmızı üretmedi**.
* Kalemin ADIYLA saydığı 12 hayalet, doğduğu seçeneklerle
  (``--cov=hrma.export.pdf_generator``) ve VARSAYILAN çekirdekle yeniden
  koşuldu — yine 0 hayalet.

Bu yüzden kapı KURULDU. Bu dosya kapının sessizce sökülmesini engeller.

Kapının kapsamı DÜRÜSTÇE sınırlıdır ve sınırı da burada kilitlidir: eşik
TAM SÜİT ölçümünden gelir, bu yüzden yalnız tam süit koşan yollara
(``tests.yml`` gecelik/elle koşum, ``release.yml`` yayın kapısı)
uygulanır. push/PR koşumu ``-m 'not agir_canli_uc'`` ile bir ALT KÜME
koşar; o alt kümenin kendi kapsam tabanı ÖLÇÜLMEDİĞİ için oraya eşik
konmaz — konsaydı kapı gerçekten "ilk gün kırmızıyla" açılırdı, yani
kalemin korktuğu şey olurdu.
"""

import json
import pathlib
import re

import coverage
import pytest
from tests.support.kanit import kanit_gerekli

yaml = pytest.importorskip(
    'yaml', reason='PyYAML iş akışı bekçilerinin bağımlılığıdır; CI onu '
                   'ayrı bir adımda kurulu olmaya ZORLAR (tests.yml).')

#: Depo kökü.
DEPO_KOKU = pathlib.Path(__file__).resolve().parents[1]
#: Kapsam yapılandırması — eşiğin TEK KAYNAĞI.
KAPSAM_CFG = DEPO_KOKU / '.coveragerc'
#: İş akışları.
TESTS_YML = DEPO_KOKU / '.github' / 'workflows' / 'tests.yml'
RELEASE_YML = DEPO_KOKU / '.github' / 'workflows' / 'release.yml'
#: Ölçüm kanıtı — eşiğin dayandığı SAYININ tek kaynağı.
KANIT = (DEPO_KOKU / 'docs' / 'scofield' / 'raw' / 'OH' / 'D25' / 'altyapi'
         / 'a1' / 'kapsam_hukmu.json')

#: Eşik ile ölçülen kapsam arasında bırakılabilecek EN BÜYÜK boşluk (puan).
#: Bu bir POLİTİKA sayısıdır, ölçüm değil: eşik ölçümün bu kadar altına
#: inebilir (gürültü + ortam farkı payı), daha aşağısı kapıyı dişsiz
#: bırakır. Ölçülen değerin kendisi KANIT dosyasındadır ve burada
#: TEKRARLANMAZ.
EN_BUYUK_BOSLUK_PUAN = 3.0


def _kanit():
    if not kanit_gerekli(KANIT).exists():
        pytest.fail(
            'Kapsam hükmü kanıtı yok: %s. Eşiğin dayandığı ölçüm depoda '
            'durmalı; yoksa .coveragerc içindeki sayı doğrulanamaz bir '
            'iddiaya döner.' % KANIT)
    return json.loads(kanit_gerekli(KANIT).read_text(encoding='utf-8'))


def _ayar(anahtar, varsayilan=None):
    """Ayarı ``coverage``\'in KENDİ ayrıştırıcısıyla okur.

    Bilerek ``configparser`` kullanılmıyor: kapı, dosyada ne YAZDIĞINA
    değil ``coverage``\'in ne OKUDUĞUNA bağlıdır. ``fail-under`` gibi tek
    harflik bir yazım hatası configparser\'a doğru görünür, coverage ise
    seçeneği hiç görmez ve eşik SESSİZCE düşer — kapının en sinsi
    fail-open biçimi budur.
    """
    if not KAPSAM_CFG.exists():
        pytest.fail('.coveragerc yok — kapsam kapısının tek kaynağı bu dosya.')
    kov = coverage.Coverage(config_file=str(KAPSAM_CFG))
    try:
        return kov.get_option(anahtar)
    except Exception:
        return varsayilan


def _isakisi(yol):
    return yaml.safe_load(yol.read_text(encoding='utf-8'))


def _kabuk_komutlari(betik):
    """Ters bölü ile devam eden kabuk satırlarını TEK satıra indirger.

    Bu birleştirme olmadan bekçi yalanır: ``pytest ... \\`` satırının
    ardından gelen ``--cov ...`` satırı AYRI bir satır gibi görünür,
    dolayısıyla hem "kapsam var mı" hem de "alt kümeye eklenmiş mi"
    denetimleri kör kalır. (Bu bekçi yazılırken gerçekten kör kaldı ve
    ölçümle yakalandı.)
    """
    birlesik, tampon = [], ''
    for ham in betik.splitlines():
        satir = ham.strip()
        if satir.endswith('\\'):
            tampon += satir[:-1].rstrip() + ' '
            continue
        birlesik.append((tampon + satir).strip())
        tampon = ''
    if tampon:
        birlesik.append(tampon.strip())
    return [s for s in birlesik if s]


def _adim(isakisi, is_adi, adim_adi):
    isler = isakisi.get('jobs', {})
    if is_adi not in isler:
        pytest.fail('İş bulunamadı: %s' % is_adi)
    for adim in isler[is_adi].get('steps', []):
        if adim.get('name') == adim_adi:
            return adim
    pytest.fail('Adım bulunamadı: %s / %s' % (is_adi, adim_adi))


# ---------------------------------------------------------------------------
# 1. Yapılandırma — kapının kendisi
# ---------------------------------------------------------------------------
class TestKapsamYapilandirmasi:
    """``.coveragerc`` kapının TEK KAYNAĞIDIR; şekli kilitlenir."""

    def test_kaynak_tum_urun_agacidir(self):
        kaynak = _ayar('run:source') or []
        assert list(kaynak) == ['hrma'], (
            'Kapsam kaynağı daraltılmış: %r. Bu yalnız yüzdeyi şişirmekle '
            'kalmaz — ÖLÇÜLDÜ (adiyla_sayilan.json): dar hedefle '
            '(--cov=hrma.export.pdf_generator) grafik/PDF kümesinde 11 '
            'kırmızı doğuyor, geniş hedefle (source = hrma) 0. P14H2-C1 '
            'kaleminin "kapı ilk gün kırmızıyla açılır" kehaneti tam olarak '
            'DAR hedefin hikâyesidir.' % (kaynak,))

    def test_esik_var_yani_kapi_fail_closed(self):
        esik = _ayar('report:fail_under')
        assert esik, (
            'coverage .coveragerc\'ten fail_under OKUMUYOR (değer: %r). '
            'Eşiksiz kapsam ölçümü kapı DEĞİLDİR: rapor basılır, kimse '
            'bakmaz, gerileme sessizce geçer.' % (esik,))

    def test_esik_dissiz_degil(self):
        """Eşik, ölçülen kapsamın çok altına indirilemez."""
        esik = float(_ayar('report:fail_under') or 0.0)
        olculen = float(_kanit()['kapsam_yuzde'])
        assert esik >= olculen - EN_BUYUK_BOSLUK_PUAN, (
            'Eşik %.2f, ölçülen kapsam %.2f — aradaki boşluk %.2f puan, '
            'izin verilen en fazla %.1f puan. Bu kadar geniş boşluk '
            'kapıyı dişsiz bırakır.'
            % (esik, olculen, olculen - esik, EN_BUYUK_BOSLUK_PUAN))

    def test_esik_ilk_gun_kirmizi_vermez(self):
        """Kalemin korktuğu şey: kapı ilk gün kırmızıyla açılır."""
        esik = float(_ayar('report:fail_under') or 0.0)
        olculen = float(_kanit()['kapsam_yuzde'])
        assert esik <= olculen, (
            'Eşik %.2f ölçülen kapsamın (%.2f) ÜSTÜNDE — kapı kurulduğu '
            'gün kırmızı verir. P14H2-C1 tam olarak bunu haber veriyordu.'
            % (esik, olculen))

    def test_omit_urun_agacini_bosaltmiyor(self):
        """``omit`` ile ürün ağacı boşaltılıp yüzde şişirilemez."""
        omit = list(_ayar('run:omit') or [])
        yasak = [d for d in omit
                 if re.fullmatch(r'hrma/\*+(\.py)?|hrma/\*\*/\*\.py|hrma/\*', d)]
        assert not yasak, (
            'omit ürün ağacının tamamını düşürüyor: %r' % (yasak,))
        assert len(omit) <= 12, (
            'omit listesi %d girdiye çıkmış. Kapsam kapısının en kolay '
            'baypası budur; büyüyen liste gerekçeli olmalı.' % len(omit))


# ---------------------------------------------------------------------------
# 2. İş akışları — kapı gerçekten koşuyor mu
# ---------------------------------------------------------------------------
class TestIsAkisiKapiyiKosuyor:

    def test_tests_yml_tam_suit_dalinda_kapsam_var(self):
        adim = _adim(_isakisi(TESTS_YML), 'pytest', 'Test paketi')
        # Tam süit dalı = işaret süzgeci OLMAYAN dal.
        komutlar = _kabuk_komutlari(adim['run'])
        tam_suit = [s for s in komutlar
                    if 'pytest tests/' in s and '-m "$HRMA_ISARET_SUZGECI"' not in s]
        assert tam_suit, 'tests.yml Test paketi adımında tam süit dalı yok'
        assert all('--cov' in s for s in tam_suit), (
            'tests.yml tam süit dalı kapsam ölçmüyor: %r. Gecelik koşum '
            'kapsam kapısının koştuğu TEK yerdir.' % (tam_suit,))

    def test_tests_yml_alt_kume_dalina_esik_uygulanmiyor(self):
        """Eşik TAM SÜİT ölçümünden geliyor; alt kümeye uygulanamaz."""
        adim = _adim(_isakisi(TESTS_YML), 'pytest', 'Test paketi')
        alt_kume = [s for s in _kabuk_komutlari(adim['run'])
                    if 'pytest tests/' in s
                    and '-m "$HRMA_ISARET_SUZGECI"' in s]
        assert alt_kume, 'push/PR (işaret süzgeçli) dal kaybolmuş'
        assert not any('--cov' in s for s in alt_kume), (
            'push/PR dalına kapsam eşiği uygulanmış: %r. O dal '
            '``agir_canli_uc`` kapısını SEÇMEZ, yani daha az kod çalıştırır; '
            'tam süit eşiği orada kaçınılmaz olarak kırmızı verir.'
            % (alt_kume,))

    def test_release_yml_yayin_kapisinda_kapsam_var(self):
        adim = _adim(_isakisi(RELEASE_YML), 'testler', 'Test paketi')
        komutlar = [s for s in _kabuk_komutlari(adim['run'])
                    if 'pytest tests/' in s]
        assert komutlar and all('--cov' in s for s in komutlar), (
            'release.yml tam süit adımı kapsam ölçmüyor — yayın, kapsam '
            'gerilemesiyle çıkabilir.')

    @pytest.mark.parametrize('yol,is_adi', [
        (TESTS_YML, 'pytest'), (RELEASE_YML, 'testler')])
    def test_kaynak_komut_satirindan_daraltilmamis(self, yol, is_adi):
        """``--cov=<modül>`` yapılandırmadaki kaynağı EZER.

        Ölçüldü: dar hedefle aynı grafik/PDF kümesi 11 kırmızı veriyor,
        geniş hedefle 0. Komut satırında değer verilmesi bu yüzden yasak;
        kaynak tek yerde, ``.coveragerc``'de durur.
        """
        adim = _adim(_isakisi(yol), is_adi, 'Test paketi')
        daraltan = [s for s in _kabuk_komutlari(adim['run'])
                    if re.search(r'--cov=(?!$|\s)', s)]
        assert not daraltan, (
            '%s / %s: kapsam kaynağı komut satırından daraltılmış: %r'
            % (yol.name, is_adi, daraltan))

    @pytest.mark.parametrize('yol,is_adi', [
        (TESTS_YML, 'pytest'), (RELEASE_YML, 'testler')])
    def test_ucuz_cekirdek_isaretlenmis(self, yol, is_adi):
        """Çekirdek yazılı olmazsa kapı pahalıya koşar ve sökülür."""
        adim = _adim(_isakisi(yol), is_adi, 'Test paketi')
        ortam = adim.get('env') or {}
        assert ortam.get('COVERAGE_CORE') == 'sysmon', (
            '%s / %s: COVERAGE_CORE=sysmon yok. Varsayılan C izleyici bu '
            'depoda x1,54-x2,09 maliyet çıkarıyor (ölçüm: %s); pahalı kapı '
            'ilk sıkışıklıkta kaldırılır.' % (yol.name, is_adi, KANIT.name))


# ---------------------------------------------------------------------------
# 3. Hüküm kanıtı — kalemin iki iddiası
# ---------------------------------------------------------------------------
class TestHukumKaniti:

    def test_kanit_dosyasi_okunur_ve_eksiksiz(self):
        k = _kanit()
        for alan in ('kapsam_yuzde', 'hayalet_kirmizilar', 'cekirdek',
                     'taban_kirmizilar', 'dilim_sayisi', 'dosya_sayisi',
                     'toplam_gecen', 'olcum_tarihi', 'cekirdek_sadakati'):
            assert alan in k, 'kanıt dosyasında %r alanı yok' % alan
        assert isinstance(k['kapsam_yuzde'], (int, float)), (
            'kapsam yüzdesi sayı değil: %r — birleştirme başarısız olmuş '
            'olabilir, eşik dayanaksız kalır.' % (k['kapsam_yuzde'],))

    def test_ucuz_cekirdek_ayni_seyi_olcuyor(self):
        """sysmon, ucuzluğu ölçüm doğruluğundan satın almamalı."""
        s = _kanit()['cekirdek_sadakati']
        assert s['yalniz_varsayilanda'] == 0, (
            'Varsayılan çekirdeğin gördüğü %d satırı sysmon GÖRMÜYOR — kapı '
            'daha az kod ölçüp daha yüksek güven veriyor demektir.'
            % s['yalniz_varsayilanda'])

    def test_tam_suitte_hayalet_kirmizi_yok(self):
        k = _kanit()
        assert k['hayalet_kirmizilar'] == [], (
            'Tam süit kapsam altında hayalet kırmızı ölçüldü: %r — kapı bu '
            'hâliyle kurulamaz.' % (k['hayalet_kirmizilar'],))

    def test_dar_hedef_olcumu_kayitli_ve_dogru_cekirdekle(self):
        """Kalemin doğduğu koşul ölçüldü mü — ve UCUZ çekirdeğe kaçılmadı mı?

        P14H2-C1 ``--cov=hrma.export.pdf_generator`` ile doğdu. O koşul
        yeniden kurulmadan "hayalet yok" demek ölçüm değil temennidir.
        """
        a = _kanit().get('adiyla_sayilan', {})
        assert a, 'adıyla sayılan hayaletlerin ölçümü kanıtta yok'
        assert a['cekirdek'] == 'varsayilan', (
            'Adıyla sayılan hayaletler UCUZ çekirdekle ölçülmüş (%r) — '
            'kalemin doğduğu koşul VARSAYILAN çekirdektir.' % (a['cekirdek'],))
        assert 'dar_hayalet_sayisi' in a and 'genis_hayalet_sayisi' in a, (
            'Ölçüm dar/geniş hedefi AYIRMIYOR; kapının tasarımı tam olarak '
            'bu ayrıma dayanıyor.')
        assert any('pdf_generator' in x for x in a['dar_hedef']['ek']), (
            'dar hedef koşumu kalemin seçeneğiyle yapılmamış: %r'
            % (a['dar_hedef']['ek'],))

    def test_kapinin_hedefinde_adiyla_sayilan_hayalet_yok(self):
        """Kapının KOŞTUĞU yapılandırmada hayalet üremiyor.

        Ölçülen ayrım (bu aşama): kalemin DAR hedefi hayaletleri gerçekten
        üretiyor; kapının GENİŞ hedefi (``source = hrma``) üretmiyor. Kapı
        bu yüzden kurulabiliyor — ve bu yüzden kaynağı daraltmak yasak.
        """
        a = _kanit().get('adiyla_sayilan', {})
        assert a['genis_hayalet_sayisi'] == 0, (
            'Kapının hedefinde (--cov=hrma) hayalet üredi: %r — kapı bu '
            'hâliyle kurulamaz.' % (a.get('genis_hayaletler'),))

    def test_dilimleme_tum_suiti_kapsadi(self):
        k = _kanit()
        assert k['dosya_sayisi'] >= 480, (
            'Ölçüm %d test dosyası kapsıyor; süit bundan büyük — hüküm '
            '"tam süit" olamaz.' % k['dosya_sayisi'])
        assert k['olculmeyen_dilim'] == [], (
            'Ölçülmeyen dilim var: %r' % (k['olculmeyen_dilim'],))


# ---------------------------------------------------------------------------
# 4. Bağımlılık — kapı temiz bir CI makinesinde GERÇEKTEN koşabiliyor mu
# ---------------------------------------------------------------------------
class TestKapininBagimliligi:
    """``pytest --cov`` eklentisiz koşulduğunda pytest 'unrecognized
    arguments' ile ÖLÜR (çıkış 4), yani eksik eklenti sessiz geçmez. Sessiz
    geçebilecek olan şey BEYANDIR: paket requirements'ta yoksa CI makinesi
    onu kurmaz ve kapı adımı her koşuda patlar.
    """

    @staticmethod
    def _beyanlar():
        metin = (DEPO_KOKU / 'requirements-dev.txt').read_text(encoding='utf-8')
        # Yorum satırları sayılmaz: bir kütüphaneyi ANMAK kurmak değildir.
        return '\n'.join(s for s in
                         (r.split('#')[0].strip() for r in metin.splitlines())
                         if s)

    @pytest.mark.parametrize('paket', ['pytest-cov', 'coverage'])
    def test_requirements_dev_beyan_ediyor(self, paket):
        assert re.search(r'^\s*%s\b' % re.escape(paket), self._beyanlar(),
                         re.IGNORECASE | re.MULTILINE), (
            '%s requirements-dev.txt\'te BEYAN EDİLMEMİŞ — CI onu kurmaz, '
            '``pytest --cov`` her koşuda çıkış 4 verir.' % paket)

    def test_sysmon_cekirdegi_icin_alt_surum_pinli(self):
        """``COVERAGE_CORE=sysmon`` eski coverage'da SESSİZCE yok sayılır."""
        m = re.search(r'^\s*coverage\s*>=\s*([\d.]+)', self._beyanlar(),
                      re.MULTILINE)
        assert m, 'coverage için alt sürüm pini yok'
        parcalar = [int(x) for x in m.group(1).split('.')[:2]]
        assert parcalar >= [7, 10], (
            'coverage alt pini %s — sysmon çekirdeği 7.10 altında kararlı '
            'değildir; pahalı izleyiciye sessizce düşülür.' % m.group(1))
