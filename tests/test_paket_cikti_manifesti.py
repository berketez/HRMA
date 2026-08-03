"""Paketin İÇİNDE ne olduğunu ve yayın kapısının onu gerçekten denetlediğini
sınayan bekçiler.

Neden bu dosya var (üçü de ölçülmüş arıza):

1. **examples/ pakete hiç girmiyordu.** Yayınlanan DMG mount edildi:
   ``Resources/app`` altında tek bir ``.hrma`` yok. Oysa ``examples/README.md``
   kullanıcıya "bu dizindeki dosyaları ``~/Documents/HRMA/projects``'e
   kopyalayın" diyor — kurulumla gelmeyen bir dizini işaret ediyordu. Hiçbir
   paketleme betiğinde ``examples`` kelimesi geçmiyordu.
2. **Paketin kökeni kanıtlanamıyordu.** Kapı yalnız dosya zamanına (mtime)
   bakıyordu; mtime "ne zaman dokunuldu" der, "hangi ağaçtan derlendi" demez.
   v2.6.25'te yayınlanan ikili, temsil ettiği commit'ten 36 dk 51 sn ÖNCE
   üretilmişti. Artık paketin içine ``BUILD_INFO.json`` gömülüyor ve kapı
   ``sha == HEAD`` karşılaştırması yapıyor.
3. **Boyut sapması ölçülmüyordu.** Bir sürümde DMG 526 MB'den 383 MB'ye düştü
   (bytecode ön-derleme kaybı); imza geçerli, uygulama açılıyor, kapı yeşildi.
   Eksik olan şey ölçülmüyordu.

Testlerin çoğu DERLEME GEREKTİRMEZ: kapı betiğinin içindeki gerçek kod
parçaları (gövde denetleyicisi, ``boyut_karsilastir``, ``manifest_denetle``)
dosyadan ÇIKARILIP sahte girdilerle çalıştırılır. Yani "betikte şu kelime
geçiyor mu" değil, "o kod doğru kararı veriyor mu" ölçülür.

Derlenmiş ağaç varsa ayrıca gerçek ``.app`` / Windows payload manifesti
denetlenir. Ağaç yoksa test ATLANIR ama atlama sebebi ve denetimin nerede
yapıldığı (yayın kapısı 8/8) mesajda açıkça beyan edilir.
"""

import json
import os
import pathlib
import re
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
PAKET = KOK / 'packaging'
KAPI = PAKET / 'release_gate.sh'
MAC_BETIK = PAKET / 'build_mac_app.sh'
WIN_BETIK = PAKET / 'build_win_payload.sh'
NSI = PAKET / 'hrma.nsi'

#: Derlenmiş .app ağacı. Başka bir ağacı denetlemek için HRMA_APP_PATH verin.
APP_YOLU = pathlib.Path(
    os.environ.get('HRMA_APP_PATH',
                   str(PAKET / 'mac' / 'build.noindex' / 'HRMA.app')))
#: Windows payload ağacı (exe'nin derlendiği kaynak).
PAYLOAD_YOLU = pathlib.Path(
    os.environ.get('HRMA_WIN_PAYLOAD', str(PAKET / 'win' / 'payload')))


def _kod(metin):
    """Kabuk yorumlarını atar — 'betiğin gövdesinde geçiyor' yanılgısına karşı.

    Kapı betiği neyin NEDEN değiştiğini uzun uzun anlatır; o cümleler koda
    bakan bir denetimi yanıltmamalı.
    """
    return '\n'.join(s for s in metin.splitlines()
                     if not s.lstrip().startswith('#'))


def _bash_fonksiyonu(metin, ad):
    """``ad() { ... }`` gövdesini kaynak dosyadan çıkarır.

    Kapının kararını veren asıl kod budur; testler onu kopyalamaz, ÇIKARIR.
    Kopyalansaydı betik değişince test eski davranışı doğrulamaya devam eder,
    yani hiçbir şey ölçmezdi.
    """
    satirlar = metin.splitlines()
    bas = None
    for i, satir in enumerate(satirlar):
        if re.match(r'^%s\s*\(\)\s*\{' % re.escape(ad), satir):
            bas = i
            break
    assert bas is not None, '%s() fonksiyonu betikte yok' % ad
    for j in range(bas + 1, len(satirlar)):
        if satirlar[j] == '}':
            return '\n'.join(satirlar[bas:j + 1])
    raise AssertionError('%s() gövdesinin sonu bulunamadı' % ad)


def _kapi_bash(govde, cagri, ortam_satirlari=()):
    """Kapıdan çıkarılan fonksiyonu sahte rapor fonksiyonlarıyla çalıştırır."""
    onsoz = [
        'set -uo pipefail',
        'PY="${PYTHON:-python3}"',
        'basarili() { echo "GECTI|$1"; }',
        'basarisiz() { echo "KALDI|$1"; }',
        'atlandi() { echo "ATLANDI|$1"; }',
    ]
    betik = '\n'.join(list(onsoz) + list(ortam_satirlari) + [govde, cagri])
    p = subprocess.run(['bash', '-c', betik], capture_output=True, text=True)
    assert p.returncode == 0, 'kabuk hatası: %s' % p.stderr
    return p.stdout


def _govde_denetleyici(tmp_path):
    """6/8 adımındaki gövde denetleyicisini kapı betiğinden çıkarır."""
    metin = KAPI.read_text(encoding='utf-8')
    m = re.search(r"cat > \"\$GOVDE_DENETI\" <<'PY'\n(.*?)\nPY\n", metin, re.S)
    assert m, 'kapıda gövde denetleyicisi (GOVDE_DENETI) bulunamadı'
    yol = tmp_path / 'govde_deneti.py'
    yol.write_text(m.group(1), encoding='utf-8')
    return yol


def _denetle(tmp_path, govde, kanit=None):
    yol = _govde_denetleyici(tmp_path)
    veri = tmp_path / 'govde.json'
    veri.write_text(json.dumps(govde), encoding='utf-8')
    cagri = ['python3', str(yol), str(veri)]
    if kanit is not None:
        cagri.append(str(kanit))
    p = subprocess.run(cagri, capture_output=True, text=True)
    return p.stdout.strip()


def _saglikli_govde(exit_mach=2.4, sarmalayici=None):
    """Sağlıklı yanıt gövdesi.

    ``sarmalayici='motor'`` gerçek hibrit yanıtının ölçülmüş şeklidir
    (2026-08-03, /calculate: ``motor.nozzle_design.performance.exit_mach``
    = 3.000; üst düzey ``nozzle_design`` null).
    """
    lule = {'nozzle_design': {'performance': {'exit_mach': exit_mach}}}
    govde = {'plots': {'performance': 'data:image/png;base64,AAA', 'motor': 'x'}}
    if sarmalayici:
        govde[sarmalayici] = lule
        govde['nozzle_design'] = None
    else:
        govde.update(lule)
    return govde


# ---------------------------------------------------------------------------
# 1) Derleme betikleri: örnekler + köken kaydı pakete giriyor mu?
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('betik', [MAC_BETIK, WIN_BETIK])
def test_betik_ornekleri_pakete_kopyalar(betik):
    kod = _kod(betik.read_text(encoding='utf-8'))
    assert re.search(r'rsync[^\n]*"\$SRC/examples"', kod), (
        '%s örnek projeleri (examples/) pakete kopyalamıyor. Yayınlanan DMG '
        'mount edilip ölçüldü: içinde tek bir .hrma yoktu, ama examples/'
        'README.md kullanıcıya o dosyaları kopyalamasını söylüyor.'
        % betik.name)
    # Sayı denetimi: bir örnek paketleme sırasında düşerse derleme durmalı.
    assert 'ORNEK_KAYNAK' in kod and 'ORNEK_PAKET' in kod, (
        '%s kopyaladığı örnek sayısını doğrulamıyor — sessiz kayıp mümkün'
        % betik.name)
    assert re.search(r'exit 1', kod), '%s hata dalında durmuyor' % betik.name


@pytest.mark.parametrize('betik', [MAC_BETIK, WIN_BETIK])
def test_betik_ornek_sayisini_sabit_yazmaz(betik):
    """Beklenen örnek sayısı depodan OKUNMALI, betiğe yazılmamalı.

    Sabit yazılırsa dördüncü örnek eklendiği gün derleme sessizce üçle devam
    eder ya da bekçi elle güncellenmek zorunda kalır.
    """
    kod = _kod(betik.read_text(encoding='utf-8'))
    assert re.search(r'ORNEK_KAYNAK="\$\(find "\$SRC/examples"', kod), (
        '%s beklenen örnek sayısını depodaki examples/*.hrma sayımından '
        'türetmiyor' % betik.name)
    assert not re.search(r'ORNEK_\w+\s*(?:=|-eq|!=)\s*"?3"?\b', kod), (
        '%s örnek sayısını sabit 3 olarak yazıyor' % betik.name)


@pytest.mark.parametrize('betik', [MAC_BETIK, WIN_BETIK])
def test_betik_build_info_gomer(betik):
    kod = _kod(betik.read_text(encoding='utf-8'))
    assert 'BUILD_INFO.json' in kod, (
        '%s pakete köken kaydı (BUILD_INFO.json) gömmüyor — hangi ağaçtan '
        'derlendiği paketten okunamaz' % betik.name)
    assert "'rev-parse', 'HEAD'" in kod or 'rev-parse HEAD' in kod, (
        '%s köken kaydına git sha yazmıyor' % betik.name)
    # Uydurma yasağı: sha ölçülemezse alan null kalmalı, sahte değer değil.
    assert 'ÖLÇÜLEMEDİ' in betik.read_text(encoding='utf-8'), (
        '%s sha okunamadığında durumu beyan etmiyor (uydurma değer riski)'
        % betik.name)


def test_build_info_yazicisi_calisir(tmp_path):
    """Betikteki BUILD_INFO üreticisi gerçekten geçerli JSON yazıyor mu?

    Betik metnini gözle doğrulamak yetmez: gömülü python bloğu çalıştırılır
    ve çıktısı ayrıştırılır.
    """
    metin = MAC_BETIK.read_text(encoding='utf-8')
    m = re.search(r'python3 - "\$RES/app/BUILD_INFO\.json"[^\n]*\\\n[^\n]*<<\'PY\'\n(.*?)\nPY\n',
                  metin, re.S)
    assert m, 'build_mac_app.sh içindeki BUILD_INFO üreticisi bulunamadı'
    uretici = tmp_path / 'build_info.py'
    uretici.write_text(m.group(1), encoding='utf-8')
    hedef = tmp_path / 'BUILD_INFO.json'
    p = subprocess.run(
        ['python3', str(uretici), str(hedef), '9.9.9', str(KOK),
         'macos-arm64', 'packaging/build_mac_app.sh'],
        capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    kayit = json.loads(hedef.read_text(encoding='utf-8'))
    assert kayit['version'] == '9.9.9'
    assert kayit['platform'] == 'macos-arm64'
    # Bu depo bir git ağacı olduğu için sha ÖLÇÜLEBİLMELİ ve HEAD'e eşit olmalı.
    head = subprocess.run(['git', '-C', str(KOK), 'rev-parse', 'HEAD'],
                          capture_output=True, text=True).stdout.strip()
    assert kayit['sha'] == head, (
        'BUILD_INFO.sha HEAD ile eşleşmiyor: %s != %s' % (kayit['sha'], head))
    assert 'basis' in ' '.join(kayit), 'köken alanlarının dayanağı beyan edilmemiş'
    assert kayit['built_at_utc'].endswith('Z')


# ---------------------------------------------------------------------------
# 2) NSIS çıktısı dist/ altına düşüyor mu?
# ---------------------------------------------------------------------------

def test_nsis_ciktisi_dist_altina_yazar():
    metin = NSI.read_text(encoding='utf-8')
    kod = '\n'.join(s for s in metin.splitlines() if not s.lstrip().startswith(';'))
    outfile = [s for s in kod.splitlines() if s.strip().startswith('OutFile')]
    assert outfile, 'hrma.nsi içinde OutFile yok'
    assert '${OUTDIR}' in outfile[0], (
        'OutFile hâlâ dizinsiz/göreli: %s — exe packaging/ altına düşer, '
        'oysa yayın kapısı ve publish_release.sh dist/ altında arar'
        % outfile[0].strip())
    assert re.search(r'!define OUTDIR "[^"]*\.\./dist"', kod), (
        'OUTDIR depo kökündeki dist/ dizinini göstermiyor')
    assert '!system' in kod and 'mkdir' in kod, (
        'dist/ yoksa oluşturulmuyor — NSIS "can\'t open output file" der')


def test_win_betigi_dist_dizinini_hazirlar():
    kod = _kod(WIN_BETIK.read_text(encoding='utf-8'))
    assert re.search(r'mkdir -p "\$SRC/dist"', kod), (
        'build_win_payload.sh makensis çıktısı için dist/ dizinini hazırlamıyor')


# ---------------------------------------------------------------------------
# 3) Kapı 8/8: içerik manifesti gerçekten karar veriyor mu?
# ---------------------------------------------------------------------------

def test_kapi_sekizinci_adimi_var():
    metin = KAPI.read_text(encoding='utf-8')
    assert re.search(r'^baslik "8/8\s', metin, re.M), (
        'yayın kapısında 8/8 (paket içerik manifesti) adımı yok')


def test_manifest_eksik_ornekte_kapiyi_kapatir(tmp_path):
    """``manifest_denetle`` sahte bir paket ağacında doğru karar veriyor mu?"""
    govde = _bash_fonksiyonu(KAPI.read_text(encoding='utf-8'), 'manifest_denetle')

    kok = tmp_path / 'paket'
    (kok / 'app' / 'examples').mkdir(parents=True)
    (kok / 'app' / 'hrma' / '__pycache__').mkdir(parents=True)
    (kok / 'app' / 'data').mkdir(parents=True)
    (kok / 'libs' / 'flask' / '__pycache__').mkdir(parents=True)
    (kok / 'app' / 'hrma' / 'app.py').write_text('x', encoding='utf-8')
    (kok / 'app' / 'launcher.py').write_text('x', encoding='utf-8')
    (kok / 'app' / 'examples' / 'generate_examples.py').write_text('x', encoding='utf-8')
    for ad in ('a', 'b', 'c'):
        (kok / 'app' / 'examples' / ('%s.hrma' % ad)).write_text('{}', encoding='utf-8')

    tam = _kapi_bash(govde, 'manifest_denetle "%s" "sahte paket"' % kok,
                     ['REPO_ORNEK=3'])
    assert 'KALDI' not in tam, 'eksiksiz paket kapıyı kapatıyor:\n%s' % tam
    assert tam.count('GECTI') >= 6, tam

    # Örnekler düşerse kapı KAPANMALI (asıl arızanın tekrarı).
    for ad in ('a', 'b', 'c'):
        (kok / 'app' / 'examples' / ('%s.hrma' % ad)).unlink()
    eksik = _kapi_bash(govde, 'manifest_denetle "%s" "sahte paket"' % kok,
                       ['REPO_ORNEK=3'])
    assert 'KALDI|sahte paket: örnek proje sayısı 0' in eksik, eksik

    # Ön-derleme kaybı da kapıyı kapatmalı (526 -> 383 MB vakası).
    import shutil
    shutil.rmtree(kok / 'libs' / 'flask' / '__pycache__')
    onderlemesiz = _kapi_bash(govde, 'manifest_denetle "%s" "sahte paket"' % kok,
                              ['REPO_ORNEK=3'])
    assert 'ön-derleme EKSİK' in onderlemesiz, onderlemesiz


def test_boyut_sapmasi_esigi_calisir(tmp_path):
    """``boyut_karsilastir``: ±%20 dışı KALDI, içi GEÇTİ, tabansız ATLANDI."""
    govde = _bash_fonksiyonu(KAPI.read_text(encoding='utf-8'), 'boyut_karsilastir')
    ortam = ['BOYUT_TOLERANS_YUZDE=20', 'TABAN_DOSYA="packaging/last_release_sizes.json"']

    artefakt = tmp_path / 'paket.dmg'
    artefakt.write_bytes(b'0' * (100 * 1024 * 1024))          # 100 MiB

    icinde = _kapi_bash(govde, 'boyut_karsilastir "%s" %d "DMG"'
                        % (artefakt, 95 * 1024 * 1024), ortam)
    assert icinde.startswith('GECTI'), icinde

    kucuk = _kapi_bash(govde, 'boyut_karsilastir "%s" %d "DMG"'
                       % (artefakt, 200 * 1024 * 1024), ortam)
    assert kucuk.startswith('KALDI'), (
        'paket tabanın yarısı kadar ama kapı geçiyor:\n%s' % kucuk)

    buyuk = _kapi_bash(govde, 'boyut_karsilastir "%s" %d "DMG"'
                       % (artefakt, 50 * 1024 * 1024), ortam)
    assert buyuk.startswith('KALDI'), buyuk

    tabansiz = _kapi_bash(govde, 'boyut_karsilastir "%s" "" "DMG"' % artefakt, ortam)
    assert tabansiz.startswith('ATLANDI') and 'DENETLENMEDİ' in tabansiz, (
        'taban yokken kapı sessizce geçiyor — denetlenmediği söylenmeli:\n%s'
        % tabansiz)

    yok = _kapi_bash(govde, 'boyut_karsilastir "%s/yok.dmg" 100 "DMG"' % tmp_path, ortam)
    assert yok.startswith('KALDI'), yok


def test_kapi_esigi_tek_yerde_tanimli():
    kod = _kod(KAPI.read_text(encoding='utf-8'))
    tanim = re.findall(r'^BOYUT_TOLERANS_YUZDE=(\d+)', kod, re.M)
    assert len(tanim) == 1, (
        'boyut toleransı %d yerde tanımlı — tek kaynak olmalı' % len(tanim))


# ---------------------------------------------------------------------------
# 4) Kapı 6/8: HTTP 200 yetmez, gövde denetleniyor mu?
# ---------------------------------------------------------------------------

def test_govde_saglikliyi_gecirir(tmp_path):
    assert _denetle(tmp_path, _saglikli_govde()) == ''


def test_govde_hibritin_gercek_seklini_tanir(tmp_path):
    """Hibrit yanıtı lüleyi ``motor.`` altında taşır (ölçüldü) — kabul edilmeli."""
    kanit = tmp_path / 'kanit.txt'
    cikti = _denetle(tmp_path, _saglikli_govde(3.0, sarmalayici='motor'), kanit)
    assert cikti == '', cikti
    assert kanit.read_text(encoding='utf-8') == \
        'motor.nozzle_design.performance.exit_mach=3.000'


def test_govde_alakasiz_exit_machi_kanit_saymaz(tmp_path):
    """Gövde baştan sona taranmamalı: rastgele bir alt nesnedeki exit_mach
    lüle çözümünün yerine geçemez."""
    govde = {'plots': {'performance': 'x'},
             'baska_bir_analiz': {'ic': {'exit_mach': 4.0}}}
    cikti = _denetle(tmp_path, govde)
    assert 'aday yolda yok' in cikti, cikti


def test_govde_eksik_performans_panosunu_yakalar(tmp_path):
    govde = _saglikli_govde()
    del govde['plots']['performance']
    cikti = _denetle(tmp_path, govde)
    assert 'plots.performance' in cikti, cikti


def test_govde_eksik_exit_machi_yakalar(tmp_path):
    """Alan YOKSA 'denetlenemedi' değil, AÇIK HATA olmalı."""
    govde = _saglikli_govde()
    del govde['nozzle_design']
    cikti = _denetle(tmp_path, govde)
    assert 'nozzle_design.performance' in cikti, cikti

    govde = _saglikli_govde()
    govde['nozzle_design']['performance'] = {}
    assert 'exit_mach' in _denetle(tmp_path, govde)


def test_govde_subsonik_lulede_kapiyi_kapatir(tmp_path):
    cikti = _denetle(tmp_path, _saglikli_govde(exit_mach=0.8))
    assert 'süpersonik değil' in cikti, cikti
    # Boolean sayı sayılmamalı (True > 1 kaçağı)
    assert 'sayı değil' in _denetle(tmp_path, _saglikli_govde(exit_mach=True))


def test_govde_bos_yaniti_yakalar(tmp_path):
    cikti = _denetle(tmp_path, {})
    assert 'plots' in cikti and 'nozzle_design' in cikti, cikti


def test_kapi_govde_denetimini_gercekten_cagirir():
    """Denetleyici dosyaya yazılıp UNUTULMAMIŞ olmalı."""
    kod = _kod(KAPI.read_text(encoding='utf-8'))
    assert '"$GOVDE_DENETI" /tmp/hrma_gate_body.json' in kod, (
        'gövde denetleyicisi üretiliyor ama duman testinde çağrılmıyor')
    assert re.search(r'GOVDE_EKSIK="\$\(.{0,300}?if \[ -z "\$GOVDE_EKSIK" \]',
                     kod, re.S), (
        'denetleyicinin çıktısı bir karara bağlanmıyor')
    # Kanıt dosyası her uçtan önce silinmeli: bir öncekinin kanıtı bir
    # sonrakinin GEÇTİ satırında görünmemeli.
    assert 'rm -f /tmp/hrma_gate_body_kanit.txt' in kod, (
        'exit_mach kanıt dosyası uçlar arasında temizlenmiyor')


# ---------------------------------------------------------------------------
# 5) Kapı 3/8: köken (BUILD_INFO.sha == HEAD)
# ---------------------------------------------------------------------------

def test_kapi_koken_karsilastirmasi_yapar():
    kod = _kod(KAPI.read_text(encoding='utf-8'))
    assert 'koken_denetle' in kod and 'BUILD_INFO.json' in kod, (
        'kapı paketin köken kaydını okumuyor — mtime tek başına hangi ağaçtan '
        'derlendiğini kanıtlamaz')
    assert '"$sha" != "$YEREL"' in kod, 'BUILD_INFO.sha HEAD ile karşılaştırılmıyor'
    assert 'hdiutil attach' in kod, 'köken kaydı DMG içinden okunmuyor'


def test_koken_denetimi_yanlis_shayi_yakalar(tmp_path):
    metin = KAPI.read_text(encoding='utf-8')
    govde = _bash_fonksiyonu(metin, 'koken_denetle')
    okuyucu = re.search(r"KOKEN_OKU='\n(.*?)\n'\n", metin, re.S)
    assert okuyucu, 'KOKEN_OKU parçası bulunamadı'
    ortam = ['YEREL=%s' % ('a' * 40), 'VERSION=9.9.9',
             "KOKEN_OKU='%s'" % okuyucu.group(1)]

    def kayit_yaz(ad, **alanlar):
        temel = {'sha': 'a' * 40, 'tree_dirty': False, 'version': '9.9.9'}
        temel.update(alanlar)
        yol = tmp_path / ad
        yol.write_text(json.dumps(temel), encoding='utf-8')
        return yol

    iyi = _kapi_bash(govde, 'koken_denetle "%s" "paket"' % kayit_yaz('iyi.json'), ortam)
    assert iyi.startswith('GECTI'), iyi

    yanlis = kayit_yaz('yanlis.json', sha='b' * 40)
    cikti = _kapi_bash(govde, 'koken_denetle "%s" "paket"' % yanlis, ortam)
    assert cikti.startswith('KALDI') and 'BAŞKA bir ağaçtan' in cikti, cikti

    kirli = kayit_yaz('kirli.json', tree_dirty=True)
    assert 'KİRLİ' in _kapi_bash(govde, 'koken_denetle "%s" "paket"' % kirli, ortam)

    bossha = kayit_yaz('bossha.json', sha=None)
    assert 'KANITSIZ' in _kapi_bash(govde, 'koken_denetle "%s" "paket"' % bossha, ortam)

    yok = _kapi_bash(govde, 'koken_denetle "%s/yok.json" "paket"' % tmp_path, ortam)
    assert yok.startswith('KALDI'), yok


# ---------------------------------------------------------------------------
# 6) Derlenmiş ağaç varsa GERÇEK manifest
# ---------------------------------------------------------------------------

def _derleme_atlama_sebebi(agac, betik):
    """Ağaç denetlenebilir mi? Değilse sebebi (beyan edilecek metin) döner."""
    if not agac.exists():
        return ('derlenmiş ağaç yok: %s — bu denetim CI\'da yapılamaz, '
                'yayın kapısının 8/8 adımı (packaging/release_gate.sh) '
                'aynı manifesti YAYINLANACAK artefakt üzerinde koşturur. '
                'Başka bir ağaç için HRMA_APP_PATH / HRMA_WIN_PAYLOAD verin.'
                % agac)
    if agac.stat().st_mtime < betik.stat().st_mtime:
        return ('ağaç güncel betikten ESKİ (%s < %s): bu paket examples/ ve '
                'BUILD_INFO.json eklenmeden önce üretilmiş. Yeniden derleyin; '
                'yayın kapısı 3/8 zaten commit\'ten eski artefaktı reddeder.'
                % (agac, betik.name))
    return None


def _ornek_sayisi(dizin):
    return len(list(dizin.glob('*.hrma'))) if dizin.is_dir() else 0


def _agac_manifesti(kok, ad):
    depo_ornek = _ornek_sayisi(KOK / 'examples')
    assert depo_ornek > 0, 'depoda examples/*.hrma yok — ölçüt kurulamıyor'

    eksik = []
    if _ornek_sayisi(kok / 'app' / 'examples') != depo_ornek:
        eksik.append('examples/*.hrma sayısı %d, depoda %d'
                     % (_ornek_sayisi(kok / 'app' / 'examples'), depo_ornek))
    for yol in ('app/launcher.py', 'app/hrma/app.py',
                'app/examples/generate_examples.py', 'app/BUILD_INFO.json'):
        if not (kok / yol).exists():
            eksik.append('%s yok' % yol)
    if not (kok / 'app' / 'data').is_dir():
        eksik.append('app/data/ yok')
    if not list((kok / 'app' / 'hrma').rglob('__pycache__')):
        eksik.append('hrma/ altında __pycache__ yok (ön-derleme kaybı)')
    assert not eksik, '%s manifesti eksik: %s' % (ad, '; '.join(eksik))

    kayit = json.loads((kok / 'app' / 'BUILD_INFO.json').read_text(encoding='utf-8'))
    assert kayit.get('sha') is None or re.fullmatch(r'[0-9a-f]{40}', kayit['sha']), (
        'BUILD_INFO.sha ne 40 haneli git sha ne de null: %r' % (kayit.get('sha'),))
    assert kayit.get('sha_basis'), 'BUILD_INFO.sha_basis beyanı yok'


def test_derlenmis_app_manifesti():
    sebep = _derleme_atlama_sebebi(APP_YOLU, MAC_BETIK)
    if sebep:
        pytest.skip(sebep)
    _agac_manifesti(APP_YOLU / 'Contents' / 'Resources', 'HRMA.app')


def test_windows_payload_manifesti():
    sebep = _derleme_atlama_sebebi(PAYLOAD_YOLU, WIN_BETIK)
    if sebep:
        pytest.skip(sebep)
    _agac_manifesti(PAYLOAD_YOLU, 'Windows payload')


def test_betikler_sozdizimsel_gecerli():
    for betik in (MAC_BETIK, WIN_BETIK, KAPI, PAKET / 'build_dmg.sh'):
        p = subprocess.run(['bash', '-n', str(betik)],
                           capture_output=True, text=True)
        assert p.returncode == 0, '%s: %s' % (betik.name, p.stderr)
