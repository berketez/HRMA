"""3.0.7 SÜREÇ — 3.0.6 yayın gününü uzatan süreç açıklarının bekçileri.

Kaynak brif: docs/scofield/raw/OH/V307/ana-model/brif_16kas/SUREC.md; kanıt ve
rapor: docs/scofield/raw/OH/V307/surec/.

Kalem 2 — aday ve paket betikleri depoda (``packaging/aday_uret.sh``,
``packaging/paket/{mac,win,ortak}.sh``). 3.0.6'da üçü de depo dışında
(``~/HRMA-calisma/2026-11-0x/_ana_model/``) ve sabit yollarla duruyordu; paket
worktree'si ayrık HEAD'deydi ve yayın kapısı 2/10 ("üst akış dalı yok")
paketler ~10 dk derlendikten SONRA kapandı. Paket betikleri artık kapı
2/10'un üç şartını derlemeden ÖNCE ölçer.

Kalem 3 — ``aday_uret.sh`` çıkış kodu. Eski son denetim satırı
``fark=$(git diff … | grep -v -E … | wc -l)`` idi: doğru adayda (dışlanmayan
fark YOK) grep 1 döner, ``set -o pipefail`` + ``set -e`` betiği öldürür; dal
üretilmiş olur ama ``aday_uret.sh N && git push … && gh workflow run …``
zinciri koşmaz. Bekçi iki durumu da koşturur: fark yok → çıkış 0 ve zincir
koşar; fark var → dal ÜRETİLMEZ, çıkış 4.

Hiçbir test ağa çıkmaz: ``origin`` geçici bir çıplak depodur, ``gh`` yerine
çağrıları diske yazan bir vekil konur.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DEPO = Path(__file__).resolve().parents[1]
ADAY = DEPO / 'packaging' / 'aday_uret.sh'
PAKET = DEPO / 'packaging' / 'paket'
YAYIN_DALI = DEPO / 'packaging' / 'yayin_dali_uret.sh'

#: Gerçek bir sürümle karışmasın diye imkânsız sürüm numarası.
SAHTE_SURUM = '9.9.9'


def _haric_varsayilani(yol):
    m = re.search(r'HARIC="\$\{HARIC:-([^}]*)\}"', yol.read_text(encoding='utf-8'))
    assert m, yol
    return m.group(1).split()


#: İç doküman dizinleri aday üreticisinin KENDİ varsayılanından okunur. Yol
#: dizgisi bu dosyada elle yazılmaz: kanıt kapısı tarayıcısı
#: (tests/support/kanit_tarayici.py) iç doküman yolu dizgisini kanıt okuması
#: sayar; buradaki yollar sahte depoya yazılan örnek dosyalardır.
IC_DIZIN = _haric_varsayilani(ADAY)
KANIT_DIZINI, TASARIM_DIZINI = IC_DIZIN[0], IC_DIZIN[2]
BASH = '/bin/bash'   # macOS'un bash 3.2'si: betikler orada da koşmalı


def _git(kok, *argumanlar):
    komut = ['git', '-C', str(kok), '-c', 'core.hooksPath=/dev/null',
             '-c', 'commit.gpgsign=false', '-c', 'user.name=sahte',
             '-c', 'user.email=sahte@ornek.invalid', *argumanlar]
    return subprocess.run(komut, check=True, capture_output=True, text=True,
                          timeout=60).stdout.strip()


def _yaz(kok, bagil, metin):
    yol = kok / bagil
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(metin, encoding='utf-8')


def _ortam(tmp_path, bin_dizin=None, **ek):
    ortam = dict(os.environ)
    for anahtar in ('TABAN', 'HARIC', 'ADAY_FETCH', 'GH_DEPO', 'PAKET_GUNLUK',
                    'MAKENSIS', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'):
        ortam.pop(anahtar, None)
    ortam['GIT_CEILING_DIRECTORIES'] = str(tmp_path)
    ortam['GIT_CONFIG_GLOBAL'] = str(tmp_path / 'gitconfig')
    ortam['GIT_AUTHOR_NAME'] = ortam['GIT_COMMITTER_NAME'] = 'sahte'
    ortam['GIT_AUTHOR_EMAIL'] = ortam['GIT_COMMITTER_EMAIL'] = 'sahte@ornek.invalid'
    if bin_dizin is not None:
        ortam['PATH'] = '%s%s%s' % (bin_dizin, os.pathsep, ortam['PATH'])
    ortam.update({k: str(v) for k, v in ek.items()})
    return ortam


def _gh_vekili(tmp_path):
    """gh yerine: argümanları kayit/gh_<n>.txt'e yazar, 0 döner."""
    kayit = tmp_path / 'kayit'
    kayit.mkdir(exist_ok=True)
    bin_dizin = tmp_path / 'bin'
    bin_dizin.mkdir(exist_ok=True)
    gh = bin_dizin / 'gh'
    gh.write_text('#!/bin/bash\n'
                  'K="%s"\n'
                  'n=$(ls "$K"/gh_*.txt 2>/dev/null | wc -l | tr -d " ")\n'
                  'printf "%%s\\n" "$@" > "$K/gh_$n.txt"\n'
                  'exit 0\n' % kayit, encoding='utf-8')
    gh.chmod(0o755)
    return bin_dizin, kayit


@pytest.fixture()
def sahte_depo(tmp_path):
    """docs'suz ``main`` (yayımlanan hat) + docs'lu ``bakim/9.9.9`` (kaynak).

    ``origin`` geçici çıplak depodur; betikler gerçek depoya hiç dokunmaz.
    """
    uzak = tmp_path / 'uzak.git'
    subprocess.run(['git', 'init', '-q', '--bare', str(uzak)], check=True,
                   capture_output=True, timeout=60)
    kok = tmp_path / 'depo'
    kok.mkdir()
    _git(kok, 'init', '-q', '-b', 'main')
    _git(kok, 'remote', 'add', 'origin', str(uzak))
    _yaz(kok, 'hrma/__init__.py', '__version__ = "9.9.8"\n')
    _yaz(kok, 'README.md', 'yayın\n')
    _git(kok, 'add', '-A')
    _git(kok, 'commit', '-q', '-m', 'yayımlanan 9.9.8 (docs yok)')
    _git(kok, 'push', '-q', 'origin', 'main')
    _git(kok, 'switch', '-q', '-c', 'bakim/%s' % SAHTE_SURUM)
    _yaz(kok, 'hrma/__init__.py', '__version__ = "%s"\n' % SAHTE_SURUM)
    _yaz(kok, 'hrma/motor.py', 'X = 1\n')
    _yaz(kok, KANIT_DIZINI + '/raw/kanit.json', '{}\n')
    _yaz(kok, TASARIM_DIZINI + '/plan.md', 'iç belge\n')
    _yaz(kok, 'docs/kilavuz/HRMA_kilavuz.md', 'kullanıcı belgesi (dışlanmaz)\n')
    _git(kok, 'add', '-A')
    _git(kok, 'commit', '-q', '-m', 'bakım: düzeltmeler + iç dokümanlar')
    shutil.copy(ADAY, kok / 'aday_uret.sh')   # izlenmeyen kopya: ağaçta değil
    _git(kok, 'switch', '-q', 'main')
    return kok


def _aday(kok, tmp_path, *argumanlar, zincir=True, bin_dizin=None, **ortam):
    komut = '%s ./aday_uret.sh %s' % (BASH, ' '.join(argumanlar))
    if zincir:
        komut += ' && echo ZINCIR_KOSTU'
    return subprocess.run([BASH, '-c', komut], cwd=str(kok), capture_output=True,
                          text=True, timeout=120,
                          env=_ortam(tmp_path, bin_dizin, **ortam))


# ---------------------------------------------------------------------------
# Kalem 3 — çıkış kodu (fark yok / fark var)
# ---------------------------------------------------------------------------

def test_aday_dogru_agacta_sifirla_cikar_ve_zincir_kosar(sahte_depo, tmp_path):
    """3.0.6 kusuru: dışlanmayan fark YOKKEN (doğru aday) çıkış 1 idi."""
    s = _aday(sahte_depo, tmp_path, '1', 'bakim/%s' % SAHTE_SURUM,
              TABAN='main', ADAY_FETCH='0')
    assert s.returncode == 0, s.stdout + s.stderr
    assert 'ZINCIR_KOSTU' in s.stdout, (
        'aday üretildi ama && zinciri koşmadı (3.0.6 çıkış kodu kusuru):\n'
        + s.stdout + s.stderr)
    assert 'kaynakla dışlanmayan fark: 0 dosya' in s.stdout
    dal = 'aday/v%s-rc.1' % SAHTE_SURUM
    dosyalar = set(_git(sahte_depo, 'ls-tree', '-r', '--name-only', dal).split())
    assert 'hrma/motor.py' in dosyalar
    assert 'docs/kilavuz/HRMA_kilavuz.md' in dosyalar        # dışlanmayan docs kalır
    assert not any(d.startswith((KANIT_DIZINI + '/', TASARIM_DIZINI + '/')) for d in dosyalar)
    # Ebeveyn yayımlanan hat (docs'lu geçmiş push geçmişine girmez).
    assert _git(sahte_depo, 'rev-parse', dal + '^') == _git(sahte_depo, 'rev-parse', 'main')
    # Kaynakla dışlanmayan ağaç aynı.
    assert _git(sahte_depo, 'diff', '--name-only', 'bakim/%s' % SAHTE_SURUM, dal,
                '--', '.', ':!' + KANIT_DIZINI, ':!' + TASARIM_DIZINI) == ''


def test_agac_denetimi_tutmazsa_dal_uretilmez(sahte_depo, tmp_path):
    """Fark VAR durumu: dışlama listesine dizin yerine DOSYA yazılırsa (gerçek
    hata biçimi) ağaçtan düşen dosya dışlanmayan fark sayılır → dal yok, 4."""
    s = _aday(sahte_depo, tmp_path, '2', 'bakim/%s' % SAHTE_SURUM,
              TABAN='main', ADAY_FETCH='0',
              HARIC='%s %s hrma/motor.py' % (KANIT_DIZINI, TASARIM_DIZINI))
    assert s.returncode == 4, s.stdout + s.stderr
    assert 'ZINCIR_KOSTU' not in s.stdout
    assert 'kaynakla dışlanmayan fark: 1 dosya' in s.stdout
    assert 'dal üretilmedi' in s.stdout
    assert _git(sahte_depo, 'branch', '--list', 'aday/*') == ''


def test_fark_sayaci_iki_durumda_da_pipefail_altinda_sifir_doner(sahte_depo, tmp_path):
    """Kökün kendisi: sayım eşleşme olsa da olmasa da boru durumunu bozmaz."""
    bakim = 'bakim/%s' % SAHTE_SURUM
    betik = ('set -euo pipefail; source ./aday_uret.sh; '
             'a=$(HARIC="%s %s docs/kilavuz hrma" '
             'disarida_kalan_fark main %s); '
             'b=$(HARIC="%s %s" disarida_kalan_fark main %s); '
             'echo "yok=$a var=$b"' % (KANIT_DIZINI, TASARIM_DIZINI, bakim,
                                       KANIT_DIZINI, TASARIM_DIZINI, bakim))
    s = subprocess.run([BASH, '-c', betik], cwd=str(sahte_depo), capture_output=True,
                       text=True, timeout=60, env=_ortam(tmp_path))
    assert s.returncode == 0, s.stdout + s.stderr
    # main → bakım: hrma/__init__.py, hrma/motor.py, docs/kilavuz/… dışlanmayan
    assert s.stdout.strip() == 'yok=0 var=3', s.stdout


def test_ayni_dal_ikinci_kez_uretilmez(sahte_depo, tmp_path):
    assert _aday(sahte_depo, tmp_path, '1', 'bakim/%s' % SAHTE_SURUM,
                 TABAN='main', ADAY_FETCH='0').returncode == 0
    s = _aday(sahte_depo, tmp_path, '1', 'bakim/%s' % SAHTE_SURUM,
              TABAN='main', ADAY_FETCH='0')
    assert s.returncode == 2 and 'dal zaten var' in s.stdout


@pytest.mark.parametrize('arguman', ['', 'x1', '1 a b', '1 --bilinmeyen', '1 bakim --ci'])
def test_bozuk_argumanlar_adla_reddedilir(sahte_depo, tmp_path, arguman):
    s = _aday(sahte_depo, tmp_path, arguman, zincir=False, TABAN='main', ADAY_FETCH='0')
    assert s.returncode == 64, s.stdout + s.stderr
    assert _git(sahte_depo, 'branch', '--list', 'aday/*') == ''


def test_push_ust_akisi_ayarlar_ve_ci_tetikler(sahte_depo, tmp_path):
    """--push: dalın üst akışı ayarlı (kapı 2/10); --ci: tests.yml o dalda."""
    bin_dizin, kayit = _gh_vekili(tmp_path)
    s = _aday(sahte_depo, tmp_path, '3', 'bakim/%s' % SAHTE_SURUM, '--push', '--ci',
              bin_dizin=bin_dizin, GH_DEPO='sahte/depo')
    assert s.returncode == 0, s.stdout + s.stderr
    assert 'ZINCIR_KOSTU' in s.stdout
    dal = 'aday/v%s-rc.3' % SAHTE_SURUM
    assert _git(sahte_depo, 'rev-parse', '--abbrev-ref', dal + '@{u}') == 'origin/' + dal
    assert _git(sahte_depo, 'rev-parse', dal + '@{u}') == _git(sahte_depo, 'rev-parse', dal)
    cagri = (kayit / 'gh_0.txt').read_text(encoding='utf-8').split()
    assert cagri == ['workflow', 'run', 'tests.yml', '--repo', 'sahte/depo', '--ref', dal]


def test_haric_kumesi_yayin_dali_ureticisiyle_ayni():
    """İki üretici aynı iç doküman kümesini dışlar (tek küme; kanıt kapısı da
    bu kümeyi tanır — tests/test_kanit_atlama_kapisi.py)."""
    from tests.support.kanit import HARIC
    assert IC_DIZIN == _haric_varsayilani(YAYIN_DALI) == list(HARIC)


# ---------------------------------------------------------------------------
# Kalem 2 — paket betikleri: kapı 2/10 ön denetimi derlemeden ÖNCE
# ---------------------------------------------------------------------------

@pytest.fixture()
def paket_agaci(sahte_depo, tmp_path):
    """Aday dalında, üst akışı ayarlı paket ağacı; derleme betikleri vekil."""
    s = _aday(sahte_depo, tmp_path, '5', 'bakim/%s' % SAHTE_SURUM, '--push',
              TABAN='main', ADAY_FETCH='0')
    assert s.returncode == 0, s.stdout + s.stderr
    dal = 'aday/v%s-rc.5' % SAHTE_SURUM
    agac = tmp_path / 'paket'
    _git(sahte_depo, 'worktree', 'add', '-q', str(agac), dal)
    # Paket betikleri + vekil derleme adımları (her biri adını günlüğe yazar).
    for ad in ('mac.sh', 'win.sh', 'ortak.sh'):
        _yaz(agac, 'packaging/paket/' + ad, (PAKET / ad).read_text(encoding='utf-8'))
    adimlar = tmp_path / 'adimlar.txt'
    for ad in ('build_mac_app.sh', 'test_bundle_mac.sh', 'build_dmg.sh',
               'build_win_payload.sh'):
        _yaz(agac, 'packaging/' + ad, 'echo %s >> "%s"\n' % (ad, adimlar))
    _yaz(agac, 'packaging/hrma.nsi', '; vekil\n')
    nsis = tmp_path / 'makensis'
    nsis.write_text('#!/bin/bash\nprintf "makensis %%s\\n" "$*" >> "%s"\n' % adimlar,
                    encoding='utf-8')
    nsis.chmod(0o755)
    _yaz(agac, '.gitignore', 'dist/\n')
    _git(agac, 'add', '-A')
    _git(agac, 'commit', '-q', '-m', 'paket betikleri (sahte)')
    _git(agac, 'push', '-q', 'origin', dal)
    return agac, adimlar, nsis


def _paket(agac, tmp_path, ad, nsis=None):
    ek = {'MAKENSIS': nsis} if nsis else {}
    return subprocess.run([BASH, str(agac / 'packaging' / 'paket' / ad)],
                          cwd=str(tmp_path), capture_output=True, text=True,
                          timeout=120, env=_ortam(tmp_path, **ek))


def test_paket_betikleri_aday_dalinda_tamamlanir(paket_agaci, tmp_path):
    agac, adimlar, nsis = paket_agaci
    mac = _paket(agac, tmp_path, 'mac.sh')
    assert mac.returncode == 0, mac.stdout + mac.stderr
    win = _paket(agac, tmp_path, 'win.sh', nsis)
    assert win.returncode == 0, win.stdout + win.stderr
    gunluk = agac / 'dist' / 'paket_gunluk'
    assert (gunluk / 'mac_durum.txt').read_text(encoding='utf-8').splitlines()[-1] == 'MAC_TAMAM'
    assert (gunluk / 'win_durum.txt').read_text(encoding='utf-8').splitlines()[-1] == 'WIN_TAMAM'
    satirlar = adimlar.read_text(encoding='utf-8').splitlines()
    assert satirlar[:3] == ['build_mac_app.sh', 'test_bundle_mac.sh', 'build_dmg.sh']
    assert satirlar[3] == 'build_win_payload.sh'
    assert satirlar[4].startswith('makensis -DVERSION=%s -DOUTDIR=%s/dist '
                                  % (SAHTE_SURUM, agac))


@pytest.mark.parametrize('bozma', ['ayrik_head', 'ust_akis_yok', 'push_edilmemis', 'kirli'])
def test_paket_on_denetimi_derlemeden_once_durur(paket_agaci, tmp_path, bozma):
    agac, adimlar, nsis = paket_agaci
    if bozma == 'ayrik_head':
        _git(agac, 'switch', '-q', '--detach')
    elif bozma == 'ust_akis_yok':
        _git(agac, 'switch', '-q', '-c', 'aday/v%s-rc.6' % SAHTE_SURUM)
    elif bozma == 'push_edilmemis':
        _yaz(agac, 'yeni.txt', 'x\n')
        _git(agac, 'add', 'yeni.txt')
        _git(agac, 'commit', '-q', '-m', 'push edilmedi')
    else:
        _yaz(agac, 'hrma/motor.py', 'X = 2\n')
    for ad in ('mac.sh', 'win.sh'):
        s = _paket(agac, tmp_path, ad, nsis)
        assert s.returncode == 8, (bozma, ad, s.stdout + s.stderr)
        assert 'PAKET AĞACI' in s.stdout
    assert not adimlar.exists(), 'ön denetim tutmadığı hâlde derleme adımı koştu'


# ---------------------------------------------------------------------------
# Kalem 1 — sürüm adı commit'i README'yi de yazar; kapı 1/10 aracın çıktısında
# geçer. Kapının denetimi betikten ÇIKARILIR (kopyalanmaz).
# ---------------------------------------------------------------------------
URETICI = DEPO / 'tools' / 'surum_commit_uret.py'
KAPI = DEPO / 'packaging' / 'release_gate.sh'
SURUM_DOSYALARI = ('hrma/__init__.py', 'hrma/data/changelog.json', 'CHANGELOG.md',
                   'README.md')


def _bash_islevi(metin, ad):
    satirlar = metin.splitlines()
    bas = next(i for i, s in enumerate(satirlar)
               if re.match(r'^%s\s*\(\)\s*\{' % re.escape(ad), s))
    son = next(j for j in range(bas + 1, len(satirlar)) if satirlar[j] == '}')
    return '\n'.join(satirlar[bas:son + 1])


def _kapi_1_10(kok):
    """Kapının 1/10 işlevini ``kok`` ağacında koşturur → (satırlar, VERSION)."""
    islev = _bash_islevi(KAPI.read_text(encoding='utf-8'), 'surum_tutarliligi_denetle')
    betik = ('set -uo pipefail\nPY="%s"\n'
             'basarili() { echo "GECTI|$1"; }\nbasarisiz() { echo "KALDI|$1"; }\n'
             '%s\nsurum_tutarliligi_denetle\necho "VERSION=$VERSION"\n'
             % (sys.executable, islev))
    s = subprocess.run([BASH, '-c', betik], cwd=str(kok), capture_output=True,
                       text=True, timeout=60)
    assert s.returncode == 0, s.stdout + s.stderr
    satirlar = s.stdout.splitlines()
    return satirlar[:-1], satirlar[-1].split('=', 1)[1]


def _surum(kok):
    return re.search(r'__version__ = "([^"]+)"',
                     (kok / 'hrma' / '__init__.py').read_text(encoding='utf-8')).group(1)


def _sonraki(surum):
    x, y, z = (int(p) for p in surum.split('.'))
    return '%d.%d.%d' % (x, y, z + 1)


def _taslaklar(tmp_path, surum):
    notu = tmp_path / 'SURUM_NOTU_TASLAK.md'
    notu.write_text(
        '<!--HRMA-LANG:en-->\n# HRMA v%(s)s — stable release: test\n\n'
        '*Released @@TARIH@@.*\n\nIntro.\n\n## Highlights\n\n- a\n\n'
        '## Updating\n\n- b\n\n<!--HRMA-LANG:tr-->\n'
        '# HRMA v%(s)s — Kararlı sürüm: deneme\n\n*Yayın tarihi: @@TARIH@@.*\n\n'
        'Giriş.\n\n## Öne çıkanlar\n\n- a\n\n## Güncelleme\n\n- b\n'
        '<!-- TASLAK: bu yorum çıktıya girmez -->\n' % {'s': surum}, encoding='utf-8')
    cl = tmp_path / 'CHANGELOG_TASLAK.md'
    cl.write_text(
        '## %(s)s — English\n\n*Released @@TARIH@@.*\n\nIntro.\n\n### Fixed\n\n- x\n\n'
        '## %(s)s — Türkçe\n\n*Yayın tarihi: @@TARIH@@.*\n\nGiriş.\n\n'
        '### Düzeltildi\n\n- x\n' % {'s': surum}, encoding='utf-8')
    return notu, cl


def _agac_kopyasi(tmp_path):
    """Bugünkü deponun sürüm dosyaları + sürüm notu, geçici ağaçta."""
    kok = tmp_path / 'agac'
    for bagil in SURUM_DOSYALARI:
        _yaz(kok, bagil, (DEPO / bagil).read_text(encoding='utf-8'))
    surum = _surum(kok)
    bagil = 'packaging/release_notes_v%s.md' % surum
    _yaz(kok, bagil, (DEPO / bagil).read_text(encoding='utf-8'))
    return kok, surum


def _uret(kok, surum, notu, cl, *ek):
    return subprocess.run(
        [sys.executable, str(URETICI), '--kok', str(kok),
         '--surum', surum, '--tarih', '2099-01-02', '--baslik', 'Stable release: test',
         '--surum-notu', str(notu), '--changelog', str(cl), *ek],
        capture_output=True, text=True, timeout=120)


def test_sonraki_surum_adi_uretilince_kapi_1_10_gecer(tmp_path):
    """Kuru koşu: bugünkü sürüm → bir sonraki (3.0.6 → 3.0.7) adı üretilir ve
    kapının 1/10 denetimi aracın çıktısında KALDI'sız geçer."""
    kok, eski = _agac_kopyasi(tmp_path)
    yeni = _sonraki(eski)
    notu, cl = _taslaklar(tmp_path, yeni)
    s = _uret(kok, yeni, notu, cl)
    assert s.returncode == 0, s.stdout + s.stderr
    satirlar, surum = _kapi_1_10(kok)
    assert surum == yeni
    assert not [x for x in satirlar if x.startswith('KALDI')], satirlar
    assert 'GECTI|README indirme linkleri %s' % yeni in satirlar
    assert 'GECTI|README sürüm satırı **HRMA v%s**' % yeni in satirlar
    readme = (kok / 'README.md').read_text(encoding='utf-8')
    assert readme.count('/releases/download/v%s/HRMA-Setup-%s' % (yeni, yeni)) == 4
    assert '/releases/download/v%s/' % eski not in readme
    notlar = (kok / 'packaging' / ('release_notes_v%s.md' % yeni)).read_text(encoding='utf-8')
    assert 'TASLAK' not in notlar and '@@' not in notlar and '2099-01-02' in notlar


def test_readme_yazilmazsa_kapi_1_10_kaldi_der(tmp_path):
    """3.0.6'nın durumu (7ac9815e1): sürüm adı var, README eski — kapı KALDI."""
    kok, eski = _agac_kopyasi(tmp_path)
    readme = (kok / 'README.md').read_text(encoding='utf-8')
    yeni = _sonraki(eski)
    notu, cl = _taslaklar(tmp_path, yeni)
    assert _uret(kok, yeni, notu, cl).returncode == 0
    (kok / 'README.md').write_text(readme, encoding='utf-8')
    satirlar, _ = _kapi_1_10(kok)
    kaldi = [x for x in satirlar if x.startswith('KALDI')]
    assert len(kaldi) == 2, satirlar
    assert 'README hâlâ eski sürümü gösteriyor' in kaldi[0]
    assert "README sürüm satırı '**HRMA v%s**' yok" % yeni in kaldi[1]


def test_tek_baglanti_dogru_digerleri_eskiyse_kapi_kaldi_der(tmp_path):
    """Eski kapı tek bir ``HRMA-Setup-<sürüm>`` geçmesini yeterli sayıyordu."""
    kok, eski = _agac_kopyasi(tmp_path)
    yeni = _sonraki(eski)
    notu, cl = _taslaklar(tmp_path, yeni)
    assert _uret(kok, yeni, notu, cl).returncode == 0
    yol = kok / 'README.md'
    metin = yol.read_text(encoding='utf-8')
    satir = next(s for s in metin.split('\n') if '/releases/download/v%s/' % yeni in s)
    eskimis = satir.replace(yeni, eski)
    yol.write_text(metin.replace(satir, eskimis, 1), encoding='utf-8')
    satirlar, _ = _kapi_1_10(kok)
    assert any(x.startswith('KALDI|README hâlâ eski sürümü') and '1 indirme' in x
               for x in satirlar), satirlar


@pytest.mark.parametrize('bozma', ['readme_uc_satir', 'taslak_yer_tutucu',
                                   'surum_kucuk', 'notu_zaten_var'])
def test_uretici_hicbir_dosya_yazmadan_durur(tmp_path, bozma):
    kok, eski = _agac_kopyasi(tmp_path)
    yeni = _sonraki(eski)
    notu, cl = _taslaklar(tmp_path, yeni)
    if bozma == 'readme_uc_satir':
        yol = kok / 'README.md'
        satirlar = yol.read_text(encoding='utf-8').split('\n')
        i = next(i for i, s in enumerate(satirlar) if '/releases/download/' in s)
        del satirlar[i]
        yol.write_text('\n'.join(satirlar), encoding='utf-8')
    elif bozma == 'taslak_yer_tutucu':
        cl.write_text(cl.read_text(encoding='utf-8') + '\n@@SAYI@@\n', encoding='utf-8')
    elif bozma == 'surum_kucuk':
        yeni = eski
    else:
        _yaz(kok, 'packaging/release_notes_v%s.md' % yeni, 'eski\n')
    once = {p: p.read_bytes() for p in kok.rglob('*') if p.is_file()}
    s = _uret(kok, yeni, notu, cl)
    assert s.returncode == 2 and 'DURDU' in s.stderr, s.stdout + s.stderr
    sonra = {p: p.read_bytes() for p in kok.rglob('*') if p.is_file()}
    assert sonra == once, 'üretici durduğu hâlde dosya yazdı'


def test_kuru_kip_dosya_yazmaz(tmp_path):
    kok, eski = _agac_kopyasi(tmp_path)
    yeni = _sonraki(eski)
    notu, cl = _taslaklar(tmp_path, yeni)
    once = {p: p.read_bytes() for p in kok.rglob('*') if p.is_file()}
    s = _uret(kok, yeni, notu, cl, '--kuru')
    assert s.returncode == 0, s.stderr
    assert s.stdout.count('yazılacak ') == 5
    assert {p: p.read_bytes() for p in kok.rglob('*') if p.is_file()} == once



# ---------------------------------------------------------------------------
# Kalem 7 — YAYIN-1/YAYIN-2 3.0.6'da kapandı (ölçüm: v3.0.6 target_commitish =
# 0dc1bef37, main o anda 0a138ff6a; kanıt gh_olcum_yayin.txt). Kalan açık:
# yayın betiği yayından SONRA README'yi yeniden yazıyordu (ağaç kirlenir,
# "commit etmeyi unutma"). Artık ağaca dokunmaz.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('readme_guncel', [True, False])
def test_yayin_betigi_readmeyi_degistirmez(tmp_path, readme_guncel):
    from tests.test_v306_yayin_sureci import SAHTE_SURUM as YS, _kostur, _yayin_tezgahi
    kok, kayit, bin_dizin, head = _yayin_tezgahi(tmp_path)
    readme = kok / 'README.md'
    if readme_guncel:
        readme.write_text('[x](https://github.com/o/r/releases/download/v%s/'
                          'HRMA-Setup-%s.exe)\n' % (YS, YS), encoding='utf-8')
        _git(kok, 'commit', '-q', '-am', 'readme')
        head = _git(kok, 'rev-parse', 'HEAD')
    once = readme.read_bytes()
    s = _kostur(kok, bin_dizin)
    assert s.returncode == 0, s.stdout + s.stderr
    assert readme.read_bytes() == once
    assert _git(kok, 'status', '--porcelain') == '', 'yayın betiği ağacı kirletti'
    assert 'ağaç değiştirilmedi' in s.stdout
    assert ('UYARI: README' in s.stdout) is (not readme_guncel)
    assert _git(kok, 'rev-parse', 'HEAD') == head


# ---------------------------------------------------------------------------
# Kalem 4 — CI hesap ortamı sabit (Linux son basamak ayrışmasının kökü:
# koşucunun işlemcisine göre numpy SIMD / OpenBLAS çekirdek seçimi).
# ---------------------------------------------------------------------------
KUNYE = DEPO / 'tools' / 'ci_hesap_kunyesi.py'


def _kunye_araci():
    import importlib.util
    spec = importlib.util.spec_from_file_location('ci_hesap_kunyesi', KUNYE)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_ci_hesap_ortami_tek_kaynaktan():
    """tests.yml (iş akışı düzeyi) ve release.yml (testler işi) sabitleri
    tools/ci_hesap_kunyesi.py SABIT_ORTAM'ın birebir aynası."""
    import yaml
    sabit = _kunye_araci().SABIT_ORTAM
    akis = DEPO / '.github' / 'workflows'
    tests_env = yaml.safe_load((akis / 'tests.yml').read_text(encoding='utf-8'))['env']
    release = yaml.safe_load((akis / 'release.yml').read_text(encoding='utf-8'))
    release_env = release['jobs']['testler']['env']
    for ad, deger in sabit.items():
        assert str(tests_env.get(ad)) == deger, ('tests.yml', ad, tests_env.get(ad))
        assert str(release_env.get(ad)) == deger, ('release.yml', ad, release_env.get(ad))
    # macOS (ARM64) paket işlerine sızmaz: release.yml'de iş akışı düzeyinde yok.
    assert not set(sabit) & set(release.get('env') or {})


def test_kunye_adimi_ve_birlesik_denetim_bagli():
    import yaml
    isler = yaml.safe_load((DEPO / '.github' / 'workflows' / 'tests.yml')
                           .read_text(encoding='utf-8'))['jobs']
    adimlar = isler['pytest']['steps']
    adlar = [a.get('name', '') for a in adimlar]
    kunye = next(a for a in adimlar if 'ci_hesap_kunyesi.py iki-kip' in (a.get('run') or ''))
    assert adlar.index(kunye['name']) < adlar.index('Test paketi')
    yukleme = next(a for a in adimlar if a.get('name', '').startswith('Test raporu'))
    assert 'ci-hesap-kunyesi.json' in yukleme['with']['path']
    son = isler['pytest-birlesik']['steps'][-1]
    assert 'ci_hesap_kunyesi.py karsilastir' in son['run'] and son.get('if') == 'always()'


def test_sondalar_testlerin_kendi_capasini_uretir():
    """Künye sondası testlerin AYNI hesabıdır: bu platformda k2 FEA değeri
    test_v306_kati_tane'nin platform çapasına, menzil test_d17'nin çapasına
    eşit (sonda testten ayrışırsa CI'daki künye yanlış şeyi ölçer)."""
    import platform as pf
    from tests.support.platform_capa import capa_rel
    from tests.test_v306_kati_tane import K2_KARTUS_FEA_CAPASI
    arac = _kunye_araci()
    anahtar = (pf.system(), pf.machine())
    from tests.support.esikler import PLATFORM_GURULTU_TABANI_REL
    # 3.0.7 (19 Kas, ana model): test_v306_kati_tane'deki karşılaştırmayla
    # AYNI kural — referans platformda (Darwin arm64) BİT-AYNI, Linux CI'da
    # koşudan koşuya ~2,3e-14 bağıl ayrışma ölçüldüğü için tek kaynaklı
    # platform gürültü tabanı (rc.2 koşu 44488954906: 0,531285564437189).
    if anahtar == ('Darwin', 'arm64'):
        assert arac.sonda_k2() == K2_KARTUS_FEA_CAPASI[anahtar]
    else:
        assert arac.sonda_k2() == pytest.approx(
            K2_KARTUS_FEA_CAPASI[anahtar], rel=PLATFORM_GURULTU_TABANI_REL)
    assert arac.sonda_menzil() == pytest.approx(735.3229283656397,
                                                rel=capa_rel(1e-9, 1e-6))


def _kunye_dosyasi(kok, dilim, model, k2, menzil, k2_sabitsiz=None):
    def kip(k2_deger):
        return {'kunye': {'islemci': {'model': model}, 'openblas': [{'cekirdek': 'Zen'}],
                          'numpy': {'etkin': ['AVX2']}},
                'olcum': {'k2_kartus_fea_yuzde': {'repr': k2_deger},
                          'ruzgarsiz_menzil_m': {'repr': menzil}}}
    yol = kok / ('pytest-report-dilim-%d' % dilim) / 'ci-hesap-kunyesi.json'
    yol.parent.mkdir(parents=True)
    yol.write_text(json.dumps({'dilim': '%d/3' % dilim, 'sabitli': kip(k2),
                               'sabitsiz': kip(k2_sabitsiz or k2)}), encoding='utf-8')


def test_karsilastir_sabitli_ayrismayi_adla_kirmizi_yapar(tmp_path):
    arac = _kunye_araci()
    _kunye_dosyasi(tmp_path, 1, 'AMD EPYC', '0.5312855644371872', '735.1',
                   k2_sabitsiz='0.5312855644371872')
    _kunye_dosyasi(tmp_path, 2, 'Intel Xeon', '0.5312855644371872', '735.1',
                   k2_sabitsiz='0.5312855644371993')
    assert arac.main(['karsilastir', '--dizin', str(tmp_path)]) == 0
    _kunye_dosyasi(tmp_path, 3, 'Intel Xeon', '0.5312855644371993', '735.1')
    assert arac.main(['karsilastir', '--dizin', str(tmp_path)]) == 1


def test_karsilastir_kunyesiz_ya_da_hatali_dilimi_kirmizi_yapar(tmp_path):
    arac = _kunye_araci()
    assert arac.main(['karsilastir', '--dizin', str(tmp_path)]) == 1
    _kunye_dosyasi(tmp_path, 1, 'AMD EPYC', '0.53', '735.1')
    yol = tmp_path / 'pytest-report-dilim-2' / 'ci-hesap-kunyesi.json'
    yol.parent.mkdir()
    yol.write_text(json.dumps({'dilim': '2/2', 'sabitli': {'hata': 'çıkış 1'},
                               'sabitsiz': {'hata': 'çıkış 1'}}), encoding='utf-8')
    assert arac.main(['karsilastir', '--dizin', str(tmp_path)]) == 1


# ---------------------------------------------------------------------------
# Kalem 5 — CI dilim süresi: ağırlıklar CI'da ölçülmüş, dilim sayısı hedefi tutar
# ---------------------------------------------------------------------------

def test_dilim_sayisi_hedefi_tutar():
    """tests.yml matris sayısı = ağırlık künyesindeki karar; ağırlıklarla
    bölünen en ağır dilim, ölçülen en yavaş koşucuda hedefin (35 dk) altında."""
    import yaml
    from tools import ci_dilim
    veri = json.loads((DEPO / 'tools' / 'ci_dilim_agirliklari.json').read_text(encoding='utf-8'))
    karar = veri['_kunye']['karar']
    matris = yaml.safe_load((DEPO / '.github' / 'workflows' / 'tests.yml')
                            .read_text(encoding='utf-8'))['jobs']['pytest']['strategy']['matrix']['dilim']
    assert len(matris) == karar['dilim_sayisi']
    agirlik, ortalama = ci_dilim.agirliklari_oku()
    atama = ci_dilim.dilimle({f: 1 for f in agirlik}, len(matris), agirlik, ortalama)
    yuk = [sum(agirlik[f] for f, k in atama.items() if k == d) for d in matris]
    en_uzun_dk = max(yuk) / 60 * karar['en_yavas_kosucu_katsayisi'] + karar['is_kurulumu_dk']
    assert en_uzun_dk <= karar['hedef_en_uzun_dilim_dk'], (
        'tahmini en uzun dilim %.1f dk > %s dk: ağırlıkları CI\'dan yeniden ölçün, '
        'sonra dilim sayısını artırın' % (en_uzun_dk, karar['hedef_en_uzun_dilim_dk']))
    # Ağırlıklar CI biriminde (medyan koşucu saniyesi): eski yerel ölçüm değil.
    assert 'CI' in veri['_kunye']['birim']
