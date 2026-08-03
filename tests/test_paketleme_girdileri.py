"""Derleme betiklerinin KOŞULSUZ okuduğu her girdi depoda gerçekten var mı?

Neden bu bekçi var (ölçülmüş iki arıza):

1. **3 Ağustos 2026, Faz 7 hazırlığı.** ``build_mac_app.sh:130`` koşulsuz
   ``cp -R "$B/mac/libs" "$RES/libs"`` yapıyordu, ama ``packaging/mac/`` dizini
   depoda YOKTU. Yani macOS paketi hiç üretilemiyordu: betik ilk çalıştırmada
   tam o satırda ölüyordu. Hiçbir test bunu görmüyordu, çünkü testler betiği
   çalıştırmıyor.
2. **1 Ağustos 2026, Faz 5.** Üç betik de ``SRC`` olarak depo dışında bir yolu
   sabit yazmıştı; o klasörde ``hrma/`` yoktu, yani paketleme BOŞ ağaçtan
   kopyalayacaktı. Aynı sınıf: betik var olmayan bir girdiye güveniyor.

Bekçinin kuralı basit: bir betik ``$B/<yol>`` biçiminde bir girdiyi kopyalama /
açma kaynağı olarak kullanıyorsa, ya o yol depoda VAR olacak, ya da kullanım
``[ -d ... ]`` / ``[ -f ... ]`` gibi bir varlık denetimiyle korunacak.

``.gitignore``'daki büyük girdiler (``win/payload``, ``runtime/*``) bilerek
depoya girmez ama makinede DURMALIDIR; onlar için ayrı, açıklayıcı bir kontrol
var — CI'da (girdiler yokken) atlanır, yerelde paketleme öncesi uyarır.
"""

import os
import re
import subprocess

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAKET = os.path.join(KOK, 'packaging')

BETIKLER = ['build_mac_app.sh', 'build_dmg.sh', 'build_win_payload.sh']

# `cp -R "$B/x/y"`, `tar -xzf "$B/runtime/z.tar.gz"`, `unzip "$B/..."` gibi
# KAYNAK kullanımları. Hedef olarak geçen "$B/..." (ör. çıktı dizini) bu
# desene takılmaz çünkü komutun ilk argümanı aranıyor.
KAYNAK = re.compile(r'\b(?:cp|rsync|tar|unzip|ditto)\b[^\n]*?"\$B/([^"]+)"')

# Varlık denetimi imzaları — bunlardan biri aynı satırda ya da yakın önceki
# satırlarda geçiyorsa kullanım "korunmuş" sayılır. Olumsuz biçimler
# (`[ ! -f x ]` → yoksa üret) ve tazelik denetimi (`-nt`) de korumadır.
KORUMA = ('[ -d ', '[ -f ', '[ -e ', '[[ -d ', '[[ -f ',
          '[ ! -d ', '[ ! -f ', '[[ ! -d ', '[[ ! -f ', ' -nt ',
          '|| true', '2>/dev/null')

# Zincirin KENDİ ürettiği yollar: depoda bulunmazlar ve bulunmamalıdırlar.
# Muafiyet körlemesine verilmiyor — aşağıdaki test her birinin gerçekten bir
# betik tarafından üretildiğini kanıtlıyor, yani yol adı değişirse muafiyet
# sessizce geçerli kalmaz.
URETILEN = {
    # build_mac_app.sh clang ile derliyor (arm64 stub), build_dmg.sh kullanmıyor
    'hrma_stub': ('build_mac_app.sh', 'clang'),
    # build_mac_app.sh'ın çıktısı; build_dmg.sh zincirde ONDAN SONRA koşar
    'mac/build.noindex': ('build_mac_app.sh', 'build.noindex'),
}


def _uretilen_mi(yol):
    return any(yol == u or yol.startswith(u + '/') for u in URETILEN)


def _betik_oku(ad):
    with open(os.path.join(PAKET, ad), encoding='utf-8') as f:
        return f.read().splitlines()


def _korumali(satirlar, i):
    """i. satırdaki kullanım bir varlık denetimiyle korunuyor mu?"""
    pencere = satirlar[max(0, i - 4):i + 1]
    return any(k in s for s in pencere for k in KORUMA)


@pytest.mark.parametrize('betik', BETIKLER)
def test_kosulsuz_girdiler_depoda_var(betik):
    satirlar = _betik_oku(betik)
    eksik = []
    for i, satir in enumerate(satirlar):
        s = satir.strip()
        if s.startswith('#'):
            continue
        for m in KAYNAK.finditer(satir):
            yol = m.group(1).rstrip('/.')
            tam = os.path.join(PAKET, yol)
            if os.path.exists(tam):
                continue
            # .gitignore'daki büyük girdiler ayrı kontrolde ele alınıyor
            if yol.startswith(('win/payload', 'runtime/')):
                continue
            # zincirin kendi ürettiği ara çıktılar girdi değildir
            if _uretilen_mi(yol):
                continue
            if _korumali(satirlar, i):
                continue
            eksik.append('%s:%d  $B/%s' % (betik, i + 1, yol))
    assert not eksik, (
        'Derleme betiği depoda OLMAYAN bir girdiyi koşulsuz okuyor; paketleme '
        'ilk çalıştırmada bu satırda ölür:\n  ' + '\n  '.join(eksik) +
        '\nYa girdiyi depoya ekleyin ya da kullanımı `[ -d ... ]` ile koruyun.')


#: Depo kökünden (``$SRC``) okunan girdiler. ``$B`` (packaging/) tarafındaki
#: girdiler yukarıda denetleniyordu ama betikler uygulama kaynaklarını depo
#: kökünden alır: ``hrma``, ``data`` ve 2026-08-03'ten beri ``examples``.
#: Birinin adı değişir de betik güncellenmezse paketleme o satırda ölür —
#: ya da (rsync'te olduğu gibi) SESSİZCE eksik paket üretir.
KAYNAK_SRC = re.compile(r'\b(?:cp|rsync|tar|unzip|ditto)\b[^\n]*?"\$SRC/([^"]+)"')


@pytest.mark.parametrize('betik', BETIKLER)
def test_kosulsuz_src_girdileri_depoda_var(betik):
    satirlar = _betik_oku(betik)
    eksik = []
    for i, satir in enumerate(satirlar):
        if satir.strip().startswith('#'):
            continue
        for m in KAYNAK_SRC.finditer(satir):
            yol = m.group(1).rstrip('/.')
            if os.path.exists(os.path.join(KOK, yol)):
                continue
            if _korumali(satirlar, i):
                continue
            eksik.append('%s:%d  $SRC/%s' % (betik, i + 1, yol))
    assert not eksik, (
        'Derleme betiği depo kökünde OLMAYAN bir kaynağı kopyalıyor:\n  '
        + '\n  '.join(eksik))


def test_ornek_projeler_iki_platforma_da_giriyor():
    """``examples/`` her iki pakete de girmeli (2026-08-03 arızası).

    Yayınlanan DMG mount edildi: ``Resources/app`` altında tek bir ``.hrma``
    yoktu. ``examples/README.md`` ise kullanıcıya o dosyaları proje dizinine
    kopyalamasını söylüyor — var olmayan bir dizini işaret ediyordu. İki
    platform aynı içeriği taşımazsa arıza yalnız birinde geri gelir.
    """
    ornekler = [a for a in os.listdir(os.path.join(KOK, 'examples'))
                if a.endswith('.hrma')]
    assert ornekler, 'examples/ altında .hrma yok — bekçinin ölçütü kalmaz'
    for betik in ('build_mac_app.sh', 'build_win_payload.sh'):
        kod = '\n'.join(s for s in _betik_oku(betik)
                        if not s.lstrip().startswith('#'))
        assert re.search(r'rsync[^\n]*"\$SRC/examples"', kod), (
            '%s örnek projeleri pakete kopyalamıyor' % betik)


def test_uretilen_muafiyetleri_hala_gecerli():
    """``URETILEN`` muafiyetleri gerçekten üretiliyor mu?

    Muafiyet listesi bir bekçinin en zayıf noktasıdır: yol adı değişir, üreten
    satır silinir, muafiyet kalır ve bekçi kör olur. Bu test her muafiyetin
    dayanağını betikte arar.
    """
    for yol, (betik, imza) in URETILEN.items():
        kaynak = '\n'.join(_betik_oku(betik))
        assert imza in kaynak, (
            "'%s' muafiyeti %s içinde '%s' üretimine dayanıyordu ama o imza "
            "artık yok. Muafiyeti kaldırın ya da güncelleyin." % (yol, betik, imza))


@pytest.mark.parametrize('betik', BETIKLER)
def test_src_depo_kokunden_tureniyor(betik):
    """``SRC`` sabit bir mutlak yola yazılmamalı (Faz 5 arızası).

    Sabit yazılırsa betik başka bir makinede ya da depo taşındığında sessizce
    yanlış ağaçtan kopyalar.
    """
    for i, satir in enumerate(_betik_oku(betik)):
        s = satir.strip()
        if s.startswith('#') or not s.startswith('SRC='):
            continue
        assert not re.match(r'SRC="?/(Users|home)/', s), (
            '%s:%d  SRC sabit mutlak yol: %s — betiğin konumundan türetin '
            '(örn. SRC="$(cd "$B/.." && pwd)")' % (betik, i + 1, s))


def test_buyuk_derleme_girdileri_yerinde():
    """``.gitignore``'daki derleme girdileri makinede duruyor mu?

    Depoya girmezler (123 MB + 35 MB), bu yüzden temiz bir klonda YOKTURLAR ve
    orada bu kontrol anlamsızdır — atlanır. Paketleme yapılacak makinede ise
    eksiklikleri sessiz bir yayın arızasına döner.
    """
    beklenen = ['win/payload', 'runtime/pbs-mac.tar.gz', 'runtime/python-embed-win.zip']
    var = [y for y in beklenen if os.path.exists(os.path.join(PAKET, y))]
    if not var:
        pytest.skip('derleme girdileri bu makinede yok (temiz klon / CI) — '
                    'paketleme yapılacaksa packaging/restore_build_inputs.sh')
    eksik = [y for y in beklenen if y not in var]
    assert not eksik, (
        'Derleme girdilerinin bir kısmı var, bir kısmı yok: eksik %s. '
        'Yarım girdi kümesiyle paketleme yarım paket üretir.' % eksik)


def test_girdiler_symlink_degil():
    """Girdiler symlink olarak durmamalı (BSD ``cp -R`` tuzağı).

    ``restore_build_inputs.sh`` girdileri ``~/.hrma-build-cache/``'e taşıyıp
    yerlerine symlink bırakabiliyor (düzenleme hızı için). BSD ``cp -R``
    symlink'i İZLEMEZ, symlink olarak kopyalar — o hâlde paketlenirse ``.app``
    içindeki ``libs`` kırık bağlantı olur ve dmg kullanıcının makinesinde
    sessizce patlar.
    """
    kirik = []
    for yol in ('win/payload', 'runtime', 'mac/libs'):
        tam = os.path.join(PAKET, yol)
        if os.path.islink(tam):
            kirik.append('%s -> %s' % (yol, os.readlink(tam)))
    assert not kirik, (
        'Derleme girdisi symlink olarak duruyor: %s. Paketlemeden ÖNCE '
        'packaging/restore_build_inputs.sh koşturun.' % kirik)


def test_betikler_sozdizimsel_gecerli():
    """``bash -n`` — betikler en azından ayrıştırılabilir olmalı."""
    for betik in BETIKLER + ['release_gate.sh', 'restore_build_inputs.sh']:
        yol = os.path.join(PAKET, betik)
        if not os.path.exists(yol):
            continue
        p = subprocess.run(['bash', '-n', yol], capture_output=True, text=True)
        assert p.returncode == 0, '%s sözdizimi hatalı:\n%s' % (betik, p.stderr)
