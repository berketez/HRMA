"""ÖH D37 / DV-UZAYTEK — ürün kimliğinden UZAYTEK markası söküldü.

Berke 23 Eyl (karar dosyası §8): "Hepsinden çıksın" — pencere başlığı
"HRMA", README/USER_MANUAL açılımından UZAYTEK çıkar, telif
"© 2026 Berke Tezgöçen". Ölçülen önce: ``hrma packaging README.md
docs/USER_MANUAL.md`` altında 27 dosyada 95 satır (büyük/küçük harf
duyarsız); motor adı yedekleri ('UZAYTEK-HRM-001', 'UZAYTEK_SOLID' ...),
CAD/PDF başlıkları, OpenRocket üretici alanı, CEA ``case=``, HTTP
User-Agent, kurulum paketi künyeleri, macOS paket kimliği ve Windows
AppUserModelID.

Bilinçli istisnalar (adıyla):
  * ``hrma/data/changelog.json`` — geçmiş sürüm notları (karar §16:
    geçmiş notuna dokunulmaz);
  * ``packaging/release_notes_v2.4.5.md`` — aynı sınıf, geçmiş sürüm notu;
  * ``/uzaytek`` rotası ve ``uzaytek.html`` şablonunun sökümünü anlatan
    satırlar (ÖH D36 söküm kaydı; marka değil, silinen sayfanın adı).
"""
import ast
import pathlib
import re
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]

TARANAN_DIZINLER = ('hrma', 'packaging')
TARANAN_DOSYALAR = ('README.md', 'docs/USER_MANUAL.md')
METIN_UZANTILARI = {'.py', '.js', '.html', '.css', '.json', '.md', '.txt',
                    '.sh', '.nsi', '.toml', '.cfg', '.ini', '.yml', '.yaml',
                    '.plist', '.xml', '.svg'}
ISTISNA_DOSYALAR = {'hrma/data/changelog.json',
                    'packaging/release_notes_v2.4.5.md'}
SOKUM_KAYDI = re.compile(r'/uzaytek\b|uzaytek\.html')
MARKA = re.compile(r'uzaytek', re.I)


#: Git'in yok saydığı derleme çıktıları (packaging/mac, win, runtime,
#: hrma_stub — 4,1 GB, eski HRMA kopyaları) ürün kaynağı değildir.
#: Ölçüldü: main ağacında tarama bunlara girince bekçi eski paket
#: kopyalarındaki markayı kırmızı sayıyordu.
DERLEME_DIZINLERI = {'__pycache__', 'mac', 'win', 'runtime', 'hrma_stub',
                     'build', 'dist'}


def _git_izlenen(ad):
    try:
        cikti = subprocess.run(['git', '-C', str(KOK), 'ls-files', '-z', '--', ad],
                               capture_output=True, check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return [KOK / y for y in cikti.decode('utf-8').split('\0') if y]


def _taranan_dosyalar():
    for ad in TARANAN_DIZINLER:
        izlenen = _git_izlenen(ad)
        if izlenen is None:  # git yok: derleme dizinleri dışındaki her şey
            izlenen = [p for p in sorted((KOK / ad).rglob('*'))
                       if not DERLEME_DIZINLERI.intersection(
                           p.relative_to(KOK / ad).parts)]
        for p in izlenen:
            if p.is_file() and p.suffix.lower() in METIN_UZANTILARI:
                yield p
    for ad in TARANAN_DOSYALAR:
        p = KOK / ad
        # docs/ yayın dalına girmez (karar §8); yoksa taranacak metin yok.
        if p.is_file():
            yield p


def marka_satirlari(kok=KOK):
    """(göreli yol, satır no, satır) — istisnalar dışındaki her eşleşme."""
    kalan = []
    for p in _taranan_dosyalar():
        goreli = p.relative_to(kok).as_posix()
        if goreli in ISTISNA_DOSYALAR:
            continue
        try:
            metin = p.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        for no, satir in enumerate(metin.splitlines(), 1):
            if MARKA.search(satir) and not SOKUM_KAYDI.search(satir):
                kalan.append((goreli, no, satir.strip()[:120]))
    return kalan


def test_urun_kaynaginda_marka_kalmadi():
    kalan = marka_satirlari()
    assert kalan == [], 'UZAYTEK ürün kaynağında kaldı: %r' % kalan[:10]


def test_istisnalar_hala_gecerli():
    """İstisna listesi bayatlarsa (dosya silinir ya da marka kalkar) bekçi
    boşuna geniş kalır — istisna yalnız gerçekten gerekenler için durur."""
    for goreli in ISTISNA_DOSYALAR:
        p = KOK / goreli
        assert p.is_file(), f'istisna dosyası yok: {goreli}'
        assert MARKA.search(p.read_text(encoding='utf-8')), (
            f'{goreli} artık markayı içermiyor — istisnadan çıkar')


def _modul_sabitleri(yol):
    agac = ast.parse(yol.read_text(encoding='utf-8'))
    sabit = {}
    for dugum in agac.body:
        if (isinstance(dugum, ast.Assign) and len(dugum.targets) == 1
                and isinstance(dugum.targets[0], ast.Name)
                and isinstance(dugum.value, ast.Constant)):
            sabit[dugum.targets[0].id] = dugum.value.value
    return sabit


def test_launcher_kimligi():
    sabit = _modul_sabitleri(KOK / 'packaging' / 'launcher.py')
    assert sabit['PENCERE_BASLIK'] == 'HRMA — Rocket Motor Analysis'
    assert sabit['APP_COPYRIGHT'] == '© 2026 Berke Tezgöçen'
    assert not MARKA.search(sabit['WIN_APP_USER_MODEL_ID'])


@pytest.mark.parametrize('motor_type,beklenen', [
    ('solid', 'HRMA_SOLID'), ('hybrid', 'HRMA_HYBRID'),
    ('liquid', 'HRMA_LIQUID')])
def test_motor_geometrisi_ad_yedegi(motor_type, beklenen):
    """Adsız geometri paketinin yedek adı nötr marka taşır (davranış)."""
    kaynak = (KOK / 'hrma' / 'export' / 'motor_geometry.py').read_text(
        encoding='utf-8')
    assert f"r.get('motor_name') or '{beklenen}'" in kaynak


def test_openrocket_uretici_alani():
    from hrma.export.openrocket_integration import OpenRocketExporter
    ex = OpenRocketExporter()
    # UI openrocket-kose 2. tur, devir D2: eski varsayılan 'HRMA-001'in '-001'i
    # OpenRocket'te gecikme sanılıp kesiliyordu (AbstractMotorLoader.removeDelay,
    # ölçüldü: 'O167-HRMA-001' -> 'O167-HRMA'). Yeni varsayılan kesilmez.
    assert ex._designation({}) == 'UNKNOWN-HRMA_001'
