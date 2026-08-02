"""macOS imza boru hattı bekçisi.

v2.6.25 otomatik güncelleme çökmesi (2026-07-28): ``packaging/build_mac_app.sh``
içindeki codesign çağrısı ``2>/dev/null || true`` ile bitiyordu, yani hata
YUTULUYORDU. Paket imzasız üretildi ve ÜÇ SÜRÜM (2.6.0/2.6.1/2.6.2) böyle
yayınlandı; macOS Tahoe sıkılaşınca ``lsd`` paketi launch-disabled kaydetti
(-67062, "code object is not signed at all"), ``open`` "executable is
missing" dedi ve güncelleme yardımcısı kullanıcıyı eski sürüme geri döndürdü.

2026-07-30'da GERÇEK 1.4 GB paket üzerinde ölçülen iki ayrı imza engeli:

1. iCloud/Finder ``.app`` köküne ``com.apple.FinderInfo`` yazıyor ve
   silindikten MİLİSANİYELER sonra geri yazıyor (``xattr -cr`` sonrası
   "temiz" doğrulandı, 30 ms sonra codesign yine "resource fork, Finder
   information, or similar detritus not allowed" verdi). Temizle-imzala
   yarışı kazanılamaz; imza ``--no-strict`` ile atılır. Bu bayrak yalnız
   imza-öncesi detritus denetimini atlar; xattr mühre girmediği için
   üretilen imza temiz ağaçtakiyle aynıdır.
2. ``Contents/MacOS`` içindeki her dosya "iç içe kod" sayılır: oradaki
   imzasız ``hrma_baslat.sh`` bundle imzasını düşürüyordu (+x bitini
   kaldırmak KURTARMIYOR — konum önemli, bit değil). Script artık
   ``Contents/Resources/`` altında (CodeResources mührüne hash ile girer),
   ``MacOS/``ta ise ona işaret eden symlink var; stub ``/bin/bash`` ile
   çağırdığı için davranış aynı.

Doğrulama tasarımı (ölçülmüş): sıkı doğrulama (``--strict``) da aynı
detritus denetimini yapar ve iCloud ağacında HER ZAMAN kırmızı kalır; bu
yüzden derleme içinde ``codesign --verify --deep`` (mühür tam kontrol),
yayın kapısında DMG içeriğinin xattr'sız kopyası üzerinde TAM SIKI
doğrulama (``--deep --strict``, ölçümde geçti) çalışır.

Bu test dosyası o hata sınıfının geri gelmesini engeller.
"""

import pathlib
import re
import shlex

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD_SH = ROOT / 'packaging' / 'build_mac_app.sh'
GATE_SH = ROOT / 'packaging' / 'release_gate.sh'

IMZA_KOMUTU = 'codesign --force --no-strict -s -'


def _komut_satirlari(metin):
    """Yorumları at, yalnız çalışan kabuk satırlarını döndür."""
    satirlar = []
    for satir in metin.splitlines():
        golge = satir.strip()
        if not golge or golge.startswith('#'):
            continue
        # Satır içi yorumu kaba ama yeterli biçimde kırp (bu betiklerde
        # '#' karakteri tırnak içinde komut olarak geçmiyor).
        satirlar.append(satir.split(' #', 1)[0])
    return satirlar


def test_codesign_hatayi_yutamaz():
    """codesign geçen hiçbir KOMUT satırı hatayı gömemez.

    Kök nedenin ta kendisi: ``codesign ... 2>/dev/null || true`` üç sürüm
    boyunca imzasız paketleri sessizce yayına taşıdı.
    """
    metin = BUILD_SH.read_text(encoding='utf-8')
    codesign_satirlari = [s for s in _komut_satirlari(metin) if 'codesign' in s]
    assert codesign_satirlari, 'build_mac_app.sh içinde codesign kalmamış!'
    for satir in codesign_satirlari:
        assert '|| true' not in satir, f'codesign hatası yutuluyor: {satir!r}'
        assert '2>/dev/null' not in satir, f'codesign stderr gömülüyor: {satir!r}'


def test_temizlik_imzadan_once_gelir():
    """.DS_Store/AppleDouble silme ve xattr temizliği imzadan ÖNCE olmalı.

    iCloud senkronu mac/libs altına .DS_Store yazıyor ve cp -R bunları
    pakete taşıyor; kullanıcıya çöp gitmemeli ve mühürlenecek ağaç
    olabildiğince sade olmalı.
    """
    metin = BUILD_SH.read_text(encoding='utf-8')
    imza = metin.index(IMZA_KOMUTU)
    assert metin.index("-name '.DS_Store' -delete") < imza, \
        '.DS_Store temizliği imzadan önce değil'
    assert metin.index("-name '._*' -delete") < imza, \
        'AppleDouble (._*) temizliği imzadan önce değil'
    assert metin.index('xattr -cr') < imza, \
        'xattr -cr temizliği imzadan önce değil'


def test_imza_no_strict_ile_atilir():
    """İmza --no-strict ile atılmalı; düz imza iCloud ağacında HEP düşer.

    Ölçüm (2026-07-30): iCloud, .app köküne FinderInfo'yu silindikten
    milisaniyeler sonra geri yazıyor; ``codesign --force -s -`` bu yüzden
    "detritus not allowed" ile başarısız oluyor. --no-strict'i kaldıran bir
    "sadeleştirme" derlemeyi yeniden kırar.
    """
    metin = BUILD_SH.read_text(encoding='utf-8')
    imza_satirlari = [s for s in _komut_satirlari(metin)
                      if 'codesign --force' in s]
    assert len(imza_satirlari) == 1, \
        f'tek bundle imza satırı beklenirdi: {imza_satirlari!r}'
    assert '--no-strict' in imza_satirlari[0]


def test_imza_dogrulamasi_imzadan_sonra_gelir():
    """codesign --verify --deep imzadan SONRA çalışmalı; --strict OLMAMALI.

    --deep doğrulama imzanın geçerliliğini ve kaynak mührünü tam kontrol
    eder ("code object is not signed at all" hâlini yakalar). --strict ise
    doğrulamada da detritus denetimi yapar ve iCloud'un geri yazdığı
    FinderInfo yüzünden derleme ağacında HER ZAMAN kırmızı kalır (ölçüldü);
    sıkı doğrulama yayın kapısında xattr'sız kopya üzerinde yapılır.
    """
    metin = BUILD_SH.read_text(encoding='utf-8')
    imza = metin.index(IMZA_KOMUTU)
    komutlar = _komut_satirlari(metin)
    dogrulamalar = [s for s in komutlar if 'codesign --verify' in s]
    assert dogrulamalar, 'build_mac_app.sh imza doğrulaması yapmıyor'
    for satir in dogrulamalar:
        assert '--deep' in satir
        assert '--strict' not in satir, \
            f'derleme içi doğrulamada --strict iCloud ağacında hep kırmızı: {satir!r}'
    assert imza < metin.index('codesign --verify --deep'), \
        'doğrulama imzadan önce'


def test_baslat_scripti_macos_dizininde_dosya_degil():
    """hrma_baslat.sh Resources'ta yaşamalı, MacOS'ta yalnız symlink olmalı.

    codesign, Contents/MacOS içindeki HER dosyayı iç içe kod sayar; imzasız
    script bundle imzasını "code object is not signed at all — In
    subcomponent" ile düşürür (+x kaldırmak kurtarmıyor, ölçüldü). Symlink
    hedef dizgesi olarak mühürlenir; gerçek dosya Resources'ta hash ile
    mühürlenir ve kaybolabilecek xattr imzası kalmaz.
    """
    metin = BUILD_SH.read_text(encoding='utf-8')
    assert 'cat > "$RES/hrma_baslat.sh"' in metin, \
        'script artık Resources altına yazılmıyor'
    assert 'ln -s ../Resources/hrma_baslat.sh' in metin, \
        'MacOS altındaki symlink kayıp'
    assert 'cat > "$APP/Contents/MacOS/hrma_baslat.sh"' not in metin, \
        'script yeniden MacOS altına dosya olarak yazılıyor — imzayı düşürür'


def test_derleme_betigi_fail_closed():
    """Betik set -e ailesiyle açılmalı ki başarısız adım derlemeyi durdursun."""
    ilk_satirlar = BUILD_SH.read_text(encoding='utf-8').splitlines()[:10]
    assert any('set -e' in s for s in ilk_satirlar), \
        'build_mac_app.sh set -e ile başlamıyor — hatalar derlemeyi durdurmaz'


def test_yayin_kapisi_imza_kontrolu_yapar():
    """Yayın kapısı .app'i, DMG içeriğini ve sıkı doğrulamayı kapsamalı."""
    metin = GATE_SH.read_text(encoding='utf-8')
    komutlar = '\n'.join(_komut_satirlari(metin))
    # Diskteki .app: --deep doğrulama
    assert 'codesign --verify --deep' in komutlar, \
        'release_gate.sh imza doğrulaması yapmıyor'
    # Yayınlanan artefakt: DMG mount edilip içi kontrol edilmeli
    assert 'hdiutil attach' in komutlar, \
        'release_gate.sh DMG içeriğini doğrulamıyor'
    # Altın standart: xattr'sız kopyada TAM SIKI doğrulama
    assert 'ditto --noextattr' in komutlar, \
        'sıkı doğrulama için xattr soyulmuş kopya alınmıyor'
    assert 'codesign --verify --deep --strict' in komutlar, \
        'DMG içeriği sıkı doğrulamadan geçirilmiyor'


def test_kapi_basliklari_tutarli():
    """Kapı başlıkları kendi içinde tutarlı ve boşluksuz numaralanmalı.

    v2.6.26: bu test kapı sayısını 6 olarak SABİTLİYORDU. Yayın kapısına
    "3/7  Yapı ↔ commit zaman sırası" eklenince (v2.6.25'te ikili, temsil
    ettiği commit'ten 36 dk 51 sn ÖNCE üretilmişti) test kırıldı — yani
    testin kilitlediği şey bir sözleşme değil, o günkü kapı sayısıydı.
    Artık payda dosyadan OKUNUR: kapı eklemek testi kırmaz, ama paydası
    farklı ya da atlanmış numara varsa kırar.
    """
    metin = GATE_SH.read_text(encoding='utf-8')
    basliklar = re.findall(r'baslik "(\d+)/(\d+)\s', metin)
    assert basliklar, 'hiç kapı başlığı bulunamadı'

    paydalar = {payda for _, payda in basliklar}
    assert len(paydalar) == 1, f'kapı başlıkları farklı payda taşıyor: {paydalar}'
    toplam = int(paydalar.pop())

    numaralar = sorted(int(n) for n, _ in basliklar)
    assert numaralar == list(range(1, toplam + 1)), \
        f'kapı numaraları 1..{toplam} aralığını boşluksuz doldurmuyor: {numaralar}'


def test_kabuk_sozdizimi_gecerli():
    """bash -n her iki betikte de geçmeli (sözdizimi bekçisi)."""
    import subprocess
    for betik in (BUILD_SH, GATE_SH):
        sonuc = subprocess.run(
            ['bash', '-n', str(betik)], capture_output=True, text=True)
        assert sonuc.returncode == 0, f'{betik.name} sözdizimi: {sonuc.stderr}'


def test_codesign_argumanlari_gecerli():
    """İmza satırı gerçekten ad-hoc bundle imzası olmalı (shlex ile ayrıştır)."""
    metin = BUILD_SH.read_text(encoding='utf-8')
    imza_satiri = next(s for s in _komut_satirlari(metin)
                       if 'codesign --force' in s)
    parcalar = shlex.split(imza_satiri)
    assert parcalar[0] == 'codesign'
    assert '--force' in parcalar
    assert '--no-strict' in parcalar
    # Ad-hoc kimlik: '-s' bayrağının değeri '-'
    s_index = parcalar.index('-s')
    assert parcalar[s_index + 1] == '-', 'ad-hoc imza (-s -) beklenmişti'
