# -*- coding: utf-8 -*-
"""ÖH Dalga-17 · kulvar ALTYAPI · aşama a1 — bekçiler.

Kapsanan defter kalemleri
-------------------------
OH-B3-04   `release.yml` ana pytest işi bütçesiz + `type=None` kör
P10B3-13   yayın kapısının içerik manifesti VARLIĞA bakıyor
P10B3-05   `hrma/run_windows.py` sabit-8080 + yabancı süreç öldürme teklifi
P10B3-23   Windows kurucusu `$INSTDIR`'ı doğrulamıyor, kaldırma tümünü siliyor
P10B3-01   görsel tur hiçbir kapıya bağlı değil
P10B3-09   ISA tablosunun ürün yüzündeki kopyaları merkezden ayrışabiliyor

Her bekçi, onarımı geçici olarak GERİ ALDIĞINDA kırmızı verecek biçimde
yazıldı; ters-mutasyon kanıtı `docs/scofield/raw/OH/D17/altyapi/a1/
mutasyon.json` dosyasındadır.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile

import pytest

DEPO = pathlib.Path(__file__).resolve().parents[1]
ISAKISI = DEPO / '.github' / 'workflows'
KAPI_BETIGI = DEPO / 'packaging' / 'release_gate.sh'


#: Görsel tur adımının BAŞLIK metni. Aşağıdaki iddialar bölümü buradan bulur.
GORSEL_TUR_BASLIGI = 'Görsel tur (tarayıcı denetim turu)'


def _adim_bolumu(metin, baslik_parcasi=GORSEL_TUR_BASLIGI):
    """Kapı adımını BAŞLIĞINDAN kes (numarasından değil).

    ÖH D28 / altyapi (defter OH-D27-04): kapıya 10. adım (iddia dili kapısı)
    eklendi ve görsel tur 9/9 iken 9/10 oldu. Buradaki iddialar bölümü
    ``metin.find('baslik "9/9')`` diye SABİT numarayla arıyordu; numara
    kayarsa ``find`` -1 döner ve ``metin[-1:]`` METNİN SON KARAKTERİNİ
    seçerdi — iddia "bulamadım" demek yerine boş bir metni ölçmeye başlardı.
    Ölçüt artık başlıktır ve bulunamazsa AÇIKÇA patlar (fail-closed).
    """
    i = metin.find(baslik_parcasi)
    assert i >= 0, f'kapıda {baslik_parcasi!r} adımı YOK'
    j = metin.rfind('baslik "', 0, i)
    assert j >= 0, f'{baslik_parcasi!r} adımının başlık satırı bulunamadı'
    return metin[j:]
NSI = DEPO / 'packaging' / 'hrma.nsi'
RUN_WINDOWS = DEPO / 'hrma' / 'run_windows.py'

if str(DEPO) not in sys.path:                      # pragma: no cover
    sys.path.insert(0, str(DEPO))

from tools.atlama_kapisi import (                  # noqa: E402
    ATLAMA_BUTCESI, TOPLANAN_TABANI, kapi)


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------

def _sentetik_junit(yol, gercek=0, modul=0, xfail=0, toplam=9500):
    """Ölçülen üç junit atlama biçimini taşıyan sentetik rapor yazar.

    Biçimler pytest 8.4 çıktısından alındı: gövde içi skip/skipif ->
    ``type='pytest.skip'``; xfail -> ``type='pytest.xfail'``; MODÜL DÜZEYİ
    atlama -> ``type`` alanı YOK.
    """
    p = [f'<testsuite name="pytest" tests="{toplam}">']
    p += [f'<testcase classname="t.a" name="s{i}">'
          f'<skipped type="pytest.skip" message="opsiyonel paket yok"/>'
          f'</testcase>' for i in range(gercek)]
    p += [f'<testcase classname="t.b" name="m{i}">'
          f'<skipped message="collection skipped">could not import</skipped>'
          f'</testcase>' for i in range(modul)]
    p += [f'<testcase classname="t.c" name="x{i}">'
          f'<skipped type="pytest.xfail" message="borc imi"/></testcase>'
          for i in range(xfail)]
    pathlib.Path(yol).write_text('\n'.join(p) + '\n</testsuite>',
                                 encoding='utf-8')
    return yol


def _temiz_tests(dizin):
    """Statik taramanın temiz geçeceği küçük bir ``tests/`` ağacı kurar.

    ÖH D37 / YB-15: kapı "kanıt yok" önekini ``tests/support/kanit.py``den
    AST ile okur ve okuyamazsa KAPANIR. Ağaca GERÇEK dosya KOPYALANIR
    (yeniden yazılmaz): bekçiler ürünün önekiyle koşar. Ağaçta
    ``docs/scofield`` yoktur, yani bu tezgâh docs'suz ağaçtır.
    """
    d = pathlib.Path(dizin) / 'tests'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'test_temiz.py').write_text(
        "import pytest\n"
        "yaml = pytest.importorskip('yaml')   # DIŞ paket — meşru\n"
        "def test_bir():\n    assert True\n", encoding='utf-8')
    (d / 'support').mkdir(exist_ok=True)
    shutil.copy(DEPO / 'tests' / 'support' / 'kanit.py',
                d / 'support' / 'kanit.py')
    return str(d)


def _adim_govdesi(is_akisi, adim_deseni):
    """İş akışındaki bir adımın `run:` gövdesini düz metin olarak döndürür."""
    metin = (ISAKISI / is_akisi).read_text(encoding='utf-8')
    m = re.search(r'- name: [^\n]*' + adim_deseni + r'[^\n]*\n(.*?)(?=\n      - name: |\Z)',
                  metin, re.S)
    return m.group(1) if m else ''


# ---------------------------------------------------------------------------
# OH-B3-04 — atlama kapısı DAVRANIŞI (yalnız yapı değil)
# ---------------------------------------------------------------------------

class TestAtlamaKapisiDavranisi:
    """Kapı, ölçülen beş kaçış yolunun beşinde de KIRMIZI vermeli.

    Ölçüm (once.json, `release.yml`in eski adımı): 300 gerçek atlama,
    12 modül düşmesi ve toplama çökmesi — üçünde de çıkış kodu 0 (YEŞİL).
    """

    def test_tam_butce_yesil_bir_fazlasi_kirmizi(self, tmp_path):
        r = _sentetik_junit(tmp_path / 'r.xml', gercek=ATLAMA_BUTCESI)
        assert kapi(r, tests_dizini=_temiz_tests(tmp_path), yaz=lambda *a: None) == [], (
            f'tam bütçe kadar ({ATLAMA_BUTCESI}) atlamada kapı kapandı — '
            'bütçe kullanılamaz derecede dar')
        r = _sentetik_junit(tmp_path / 'r.xml', gercek=ATLAMA_BUTCESI + 1)
        assert kapi(r, tests_dizini=_temiz_tests(tmp_path), yaz=lambda *a: None), (
            f'{ATLAMA_BUTCESI + 1} atlama bütçeyi aştı ama kapı AÇIK kaldı — '
            'eşik yalnız bilgi basıyor (OH-B3-04 kusurunun tam kendisi)')

    def test_xfail_butceyi_yemez(self, tmp_path):
        r = _sentetik_junit(tmp_path / 'r.xml', gercek=ATLAMA_BUTCESI, xfail=200)
        assert kapi(r, tests_dizini=_temiz_tests(tmp_path), yaz=lambda *a: None) == [], (
            '200 xfail bütçeye sayıldı — borç imleri atlama değildir; junit '
            'ikisini de <skipped> yazar, ayırt edici alan `type`')

    def test_tek_modul_dusmesi_bile_kirmizi(self, tmp_path):
        r = _sentetik_junit(tmp_path / 'r.xml', gercek=1, modul=1)
        hata = kapi(r, tests_dizini=_temiz_tests(tmp_path), yaz=lambda *a: None)
        assert any('MODUL' in h for h in hata), (
            'bir MODÜL toplama düzeyinde düştü (junit`te `type` alanı olmayan '
            'tek satır) ama kapı açık kaldı — release.yml`in eski adımının '
            'ölçülen kör noktası (12 modül düşmesinde çıkış 0)')

    def test_toplama_cokmesi_kirmizi(self, tmp_path):
        r = _sentetik_junit(tmp_path / 'r.xml', toplam=TOPLANAN_TABANI - 1)
        hata = kapi(r, tests_dizini=_temiz_tests(tmp_path), yaz=lambda *a: None)
        assert any('toplandi' in h for h in hata), (
            'toplama çöktü ("0 test, 0 atlama") ama kapı açık kaldı')

    def test_rapor_yoksa_kapi_KAPANIR(self, tmp_path):
        """FAIL-CLOSED: "ölçemedim" yeşile sayılmaz.

        Eski adım rapor yoksa `print('rapor yok'); raise SystemExit(0)`
        diyordu — test adımı raporu üretmeden düştüğünde yayın kapısı yeşil
        çıkıyordu.
        """
        hata = kapi(str(tmp_path / 'yok.xml'),
                    tests_dizini=_temiz_tests(tmp_path), yaz=lambda *a: None)
        assert hata and 'OLCULEMIYOR' in hata[0], hata

    def test_depo_ici_importorskip_kirmizi(self, tmp_path):
        d = pathlib.Path(_temiz_tests(tmp_path))
        (d / 'test_depo_ici.py').write_text(
            "import pytest\n"
            "m = pytest.importorskip('hrma.app')   # DEPO-İÇİ — yasak\n",
            encoding='utf-8')
        r = _sentetik_junit(tmp_path / 'r.xml', gercek=1)
        hata = kapi(r, tests_dizini=str(d), yaz=lambda *a: None)
        assert any('importorskip' in h for h in hata), hata


class TestReleaseYmlKapiyaBagli:
    """`release.yml` kapıyı GERÇEKTEN çağırıyor ve bütçe TEK yerde yazılı."""

    def test_release_yml_atlama_kapisini_cagiriyor(self):
        govde = _adim_govdesi('release.yml', r'Atlama')
        assert 'tools/atlama_kapisi.py' in govde, (
            'release.yml`in atlama adımı `tools/atlama_kapisi.py`yi '
            f'çağırmıyor — OH-B3-04 geri gelmiş olabilir. Gövde:\n{govde[:400]}')

    def test_release_yml_bilgi_amacli_adimi_KALMADI(self):
        metin = (ISAKISI / 'release.yml').read_text(encoding='utf-8')
        # Adım ADI aranır, düz metin değil: gerekçe yorumu eski adımın adını
        # BİLEREK alıntılıyor (neyin neden değiştiği okunabilsin diye).
        adlar = re.findall(r'- name: ([^\n]*)', metin)
        assert not [a for a in adlar if 'bilgi amaçlı' in a], (
            f'bütçesiz "bilgi amaçlı" atlama envanteri adımı geri gelmiş '
            f'({adlar}) — yayın kapısı yine sıfır atlama korumasıyla koşuyor')

    def test_butce_tests_yml_de_YENIDEN_TANIMLANMIYOR(self):
        """TEK KAYNAK — ÖH D21 / defter OH-D17-19 ile TAMAMLANDI.

        D17'de bu bekçi "iki yerde yazılı ama AYNI sayı" diyordu; ayrışmayı
        yakalıyordu ama iki tanım noktasını kabulleniyordu. D21'de ikinci
        tanım noktası kaldırıldı: `tests.yml`in ana `pytest` işi üç eşiği de
        (`ATLAMA_BUTCESI`, `TOPLANAN_TABANI`, `DEPO_KOKLERI`)
        `tools/atlama_kapisi.py`den AST ile okuyor. Bekçi buna göre ÇEVRİLDİ:
        artık sayının EŞİT olmasını değil, YENİDEN YAZILMAMIŞ olmasını
        arıyor — eşitlik iddiası, kopyanın var olmasını gerektirdiği için
        kusuru koruyordu.
        """
        metin = (ISAKISI / 'tests.yml').read_text(encoding='utf-8')
        for ad in ('BUTCE', 'TOPLANAN_TABANI', 'DEPO_KOKLERI'):
            kopyalar = re.findall(r'^\s*%s\s*=\s*([\'"(\d][^\n]*)$' % ad,
                                  metin, re.M)
            sabitler = [k for k in kopyalar if not k.startswith('_esik(')]
            assert not sabitler, (
                f'tests.yml içinde {ad} SABİT olarak yeniden tanımlanmış '
                f'({sabitler}) — tek kaynak tools/atlama_kapisi.py; '
                'değeri orada güncelleyin, burada kopyalamayın.')
        # ...ve gerçekten oradan okuyor olmalı (boş bir gövde de yukarıdaki
        # iddiayı geçerdi; bu satır kapıyı fail-closed tutar).
        assert 'tools/atlama_kapisi.py' in metin, (
            'tests.yml bütçeyi tek kaynaktan OKUMUYOR — eşikler kayboldu, '
            'adım eşiksiz koşuyor olabilir.')
        assert ATLAMA_BUTCESI > 0


# ---------------------------------------------------------------------------
# P10B3-13 — paket içerik manifesti İÇERİĞE bakıyor mu
# ---------------------------------------------------------------------------

def _manifest_bolgesi():
    """Kapının REPO_* tabanları + `manifest_denetle` gövdesini çıkarır."""
    metin = KAPI_BETIGI.read_text(encoding='utf-8')
    i0 = metin.find('REPO_ORNEK="$(find')
    i = metin.find('manifest_denetle() {')
    j = metin.find('\n}\n', i)
    assert i0 >= 0 and i > i0 and j > i, 'manifest bölgesi bulunamadı'
    return metin[i0:j + 3]


def _sahte_paket(kok, bayt=0):
    """Her dosyası `bayt` uzunluğunda, `data/` BOŞ bir paket ağacı kurar."""
    kok = pathlib.Path(kok)
    for alt in ('app/examples', 'app/hrma/__pycache__', 'app/data',
                'libs/__pycache__'):
        (kok / alt).mkdir(parents=True, exist_ok=True)
    dolgu = b'x' * bayt
    for f in ('app/launcher.py', 'app/hrma/app.py',
              'app/examples/generate_examples.py'):
        (kok / f).write_bytes(dolgu)
    for n in range(len(list((DEPO / 'examples').glob('*.hrma')))):
        (kok / 'app/examples' / f'o{n}.hrma').write_bytes(dolgu)
    return kok


def _manifesti_kos(paket_kok, src=None):
    """Manifest bölgesini koşar. `src` verilmezse depo kökü kullanılır.

    ÖH D19 (Fable-D17 P10B3-13 ŞARTI): `REPO_DATA` tabanının kaynağını
    değiştirebilmek için `SRC` dışarıdan verilebilir hâle getirildi; mevcut
    çağrılar varsayılanla aynen çalışır.
    """
    src = DEPO if src is None else src
    betik = f'''
set -u
HATA_SAYISI=0
SRC="{src}"
basarili() {{ printf "  GECTI  %s\\n" "$1"; }}
basarisiz() {{ printf "  KALDI  %s\\n" "$1"; HATA_SAYISI=$((HATA_SAYISI + 1)); }}
atlandi() {{ printf "  ATLANDI %s\\n" "$1"; }}
{_manifest_bolgesi()}
HATA_SAYISI=0
manifest_denetle "{paket_kok}" "SAHTE PAKET"
echo "HATA_SAYISI=$HATA_SAYISI"
'''
    r = subprocess.run(['bash', '-c', betik], capture_output=True, text=True,
                       timeout=180)
    cik = r.stdout + r.stderr
    m = re.search(r'HATA_SAYISI=(\d+)', cik)
    return (int(m.group(1)) if m else -1), cik


@pytest.mark.skipif(shutil.which('bash') is None, reason='bash yok')
class TestPaketIcerikManifesti:

    def test_sifir_baytlik_sahte_paket_KALIR(self, tmp_path):
        """Ölçüldü (once.json): bu ağaç 6/6 GEÇİYORDU, HATA_SAYISI=0.

        Ağaç: launcher.py / hrma/app.py / generate_examples.py ve depodaki
        kadar `.hrma` — hepsi 0 BAYT; `app/data/` BOŞ dizin; `__pycache__`
        dizinleri BOŞ. Kapının yazılma gerekçesi olan iki kaybın (examples/
        yok, 526->383 MB bytecode) ikisi de NİCELİK kaybıydı.
        """
        hata, cik = _manifesti_kos(_sahte_paket(tmp_path / 'sahte'))
        # ALTI sınamanın ALTISI da kalmalı: tek bir sınama `-f`/`-d` biçimine
        # geri dönerse bu bekçi kırmızı verir (ters mutasyonla ölçüldü).
        assert hata == 6, (
            f'0 baytlık / boş data`lı sahte paket yalnız {hata}/6 sınamada '
            f'kaldı — en az bir sınama hâlâ VARLIĞA bakıyor:\n{cik}')
        for beklenen in ('data/', 'launcher.py', 'ön-derleme'):
            assert beklenen in cik, f'{beklenen!r} sınaması çıktıda yok:\n{cik}'

    def test_bos_data_dizini_tek_basina_KALIR(self, tmp_path):
        """`data/` boşken paket katalogsuz açılır — "yerinde" hükmü yalandır."""
        kok = _sahte_paket(tmp_path / 'yarim', bayt=4096)
        # .pyc ekle ki yalnız data/ eksikliği ölçülsün
        (kok / 'app/hrma/__pycache__/app.cpython-312.pyc').write_bytes(b'x' * 64)
        (kok / 'libs/__pycache__/x.cpython-312.pyc').write_bytes(b'x' * 64)
        hata, cik = _manifesti_kos(kok)
        assert hata >= 1 and 'data/ EKSİK' in cik, (
            f'boş `data/` dizini kapıdan geçti:\n{cik}')

    def test_dolu_paket_GECER(self, tmp_path):
        """Karşı yön: gerçekten dolu bir paket kapıdan geçmeli.

        Bu olmadan bekçi "her şeyi reddet" biçimine kayabilir ve hiçbir şey
        ölçmez.
        """
        kok = _sahte_paket(tmp_path / 'tam', bayt=4096)
        hedef = kok / 'app/data'
        for p in sorted((DEPO / 'data').rglob('*')):
            if p.is_file():
                (hedef / p.relative_to(DEPO / 'data')).parent.mkdir(
                    parents=True, exist_ok=True)
                (hedef / p.relative_to(DEPO / 'data')).write_bytes(b'x' * 128)
        (kok / 'app/hrma/__pycache__/app.cpython-312.pyc').write_bytes(b'x' * 64)
        (kok / 'libs/__pycache__/x.cpython-312.pyc').write_bytes(b'x' * 64)
        hata, cik = _manifesti_kos(kok)
        assert hata == 0, f'dolu paket kapıdan geçmedi:\n{cik}'

    @pytest.mark.skipif(shutil.which('git') is None, reason='git yok')
    def test_onbellek_dosyasi_YANLIS_KIRMIZI_vermez(self, tmp_path):
        """ÖH D19 — Fable-D17 P10B3-13 ŞARTI: taban DETERMİNİSTİK olmalı.

        Ölçüldü (`docs/scofield/raw/OH/D19/altyapi/a1/once_p10b3_13.json`):
        taban `find "$SRC/data" -type f` ile ÇALIŞMA AĞACINDAN sayılıyordu.
        `data/propellant_cache/*.json` gitignore'lu bir ÇALIŞMA ZAMANI
        önbelleğidir (yazan: `hrma/data/web_propellant_api.py`) ve pakete
        girmez; `experimental_data.db` ise rsync'te AÇIKÇA dışlanır. İkisi de
        tabanı şişiriyor, paket sabit kalıyordu → "data/ EKSİK" YANLIŞ
        KIRMIZISI (sahte depoda taban 32→87, paket 86). Kapının kendi 6/9
        canlı duman testi paket derlendikten SONRA önbelleğe yazınca taban
        87→90 oluyor, kırmızı 8/9'da KALIYORDU.
        """
        depo = tmp_path / 'depo'
        (depo / 'data').mkdir(parents=True)
        (depo / 'examples').mkdir()
        for i in range(32):
            (depo / 'data' / f'katalog_{i}.json').write_text(
                '{"x": 1}', encoding='utf-8')
        for n in range(len(list((DEPO / 'examples').glob('*.hrma')))):
            (depo / 'examples' / f'o{n}.hrma').write_text('x' * 128,
                                                          encoding='utf-8')
        for komut in (f'git init -q "{depo}"',
                      f'git -C "{depo}" config user.email a@b',
                      f'git -C "{depo}" config user.name a',
                      f'git -C "{depo}" add -A',
                      f'git -C "{depo}" commit -qm ilk'):
            subprocess.run(['bash', '-c', komut], capture_output=True,
                           timeout=120)
        # Paket: derlemenin kopyaladığı küme (izlenen 32 dosya)
        kok = _sahte_paket(tmp_path / 'paket', bayt=4096)
        (kok / 'app/data').mkdir(parents=True, exist_ok=True)
        for i in range(32):
            (kok / 'app/data' / f'katalog_{i}.json').write_text(
                '{"x": 1}', encoding='utf-8')
        (kok / 'app/hrma/__pycache__/app.cpython-312.pyc').write_bytes(b'x' * 64)
        (kok / 'libs/__pycache__/x.cpython-312.pyc').write_bytes(b'x' * 64)
        hata, cik = _manifesti_kos(kok, src=depo)
        assert hata == 0, f'temiz ağaçta dolu paket kapıdan geçmedi:\n{cik}'
        # Şimdi ÇALIŞMA AĞACINA izlenmeyen önbellek + db yaz: paket aynı.
        (depo / 'data' / 'propellant_cache').mkdir()
        for i in range(54):
            (depo / 'data' / 'propellant_cache' / f'{i}.json').write_text(
                '{}', encoding='utf-8')
        (depo / 'data' / 'experimental_data.db').write_text('x' * 4096,
                                                            encoding='utf-8')
        hata2, cik2 = _manifesti_kos(kok, src=depo)
        assert 'data/ EKSİK' not in cik2, (
            'çalışma zamanı önbelleği tabanı şişirdi, kapı YANLIŞ KIRMIZI '
            f'verdi — taban depodan (git indeksinden) türetilmiyor:\n{cik2}')
        assert hata2 == 0, (
            f'önbellek eklendikten sonra kapı {hata2} sınamada kaldı:\n{cik2}')


# ---------------------------------------------------------------------------
# P10B3-05 — Windows başlatıcısının port davranışı
# ---------------------------------------------------------------------------

class TestWindowsBaslaticiPortu:

    def test_kodda_sabit_8080_KALMADI(self):
        """Ölçüldü (once.json): 11 KOD satırında 8080 sabiti vardı."""
        satirlar = [(i + 1, s) for i, s in
                    enumerate(RUN_WINDOWS.read_text(encoding='utf-8').split('\n'))
                    if '8080' in s and not s.strip().startswith('#')]
        assert not satirlar, (
            'run_windows.py kod satırlarında sabit 8080 var: '
            f'{[n for n, _ in satirlar]} — port `hrma.run.pick_port` üzerinden '
            'tek kaynaktan gelmeli')

    def test_yabanci_sureci_oldurme_teklifi_KALMADI(self):
        metin = RUN_WINDOWS.read_text(encoding='utf-8')
        kod = '\n'.join(s for s in metin.split('\n')
                        if not s.strip().startswith('#'))
        for yasak in ('taskkill', 'kill_process_on_port',
                      'Kill existing process'):
            assert yasak not in kod, (
                f'{yasak!r} geri gelmiş — başlatıcı kullanıcının BAŞKA '
                'uygulamasını sonlandırmayı teklif ediyor (P10B3-05)')

    def test_8080_doluyken_yedek_porta_KACAR(self):
        """Ürün davranışı: 8080'i bir başkası tutuyorsa 8081'e geçilmeli."""
        import hrma.run_windows as rw
        tutucu = socket.socket()
        tutucu.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            tutucu.bind(('127.0.0.1', 8080))
            tutucu.listen(1)
        except OSError:                            # pragma: no cover
            pytest.skip('8080 bu makinede bağlanamıyor (başka bir süreç tutuyor)')
        eski = os.environ.pop('HRMA_PORT', None)
        try:
            port = rw.secilen_port()
            assert port != 8080, (
                '8080 doluyken başlatıcı yine 8080 döndü — kaçış yok')
            assert port in rw.PORT_RANGE, port
        finally:
            tutucu.close()
            if eski is not None:
                os.environ['HRMA_PORT'] = eski

    def test_port_araligi_run_py_ile_AYNI(self):
        import hrma.run as r
        import hrma.run_windows as rw
        assert rw.PORT_RANGE is r.PORT_RANGE, (
            'iki giriş noktası ayrı port aralığı taşıyor — v2.6.2 CORS '
            'kazasının kalıbı (aynı bilgi iki dosyada, biri diğerini bilmiyor)')


# ---------------------------------------------------------------------------
# P10B3-23 — Windows kurucusu $INSTDIR doğrulaması
# ---------------------------------------------------------------------------

class TestKurucuDizinDogrulamasi:

    @staticmethod
    def _kod():
        return '\n'.join(s for s in NSI.read_text(encoding='utf-8').split('\n')
                         if not s.lstrip().startswith(';'))

    def test_onVerifyInstDir_var(self):
        assert '.onVerifyInstDir' in self._kod(), (
            'kurucu seçilen dizini DOĞRULAMIYOR — kullanıcı Browse ile '
            'D:\\Projeler seçerse kurulum oradaki app/libs/python klasörlerini '
            'uyarısız siler (P10B3-23)')

    def test_kosulsuz_INSTDIR_silme_KALMADI(self):
        kod = self._kod()
        assert not re.search(r'RMDir\s+/r\s+"\$INSTDIR"\s*(;.*)?$', kod, re.M), (
            'kaldırma $INSTDIR`ın TAMAMINI koşulsuz siliyor — geri dönüşsüz')

    @staticmethod
    def _bolum(kod, basi):
        """`Section ...` ... `SectionEnd` dilimini döndürür (yorumlar sökülü).

        ÖH D19 (Fable-D17 P10B3-23 ŞARTI (1)): iddialar DOSYANIN TAMAMINDA
        aranırsa kapsam ayırt edilmez. Ölçüldü: kaldırma bölümündeki
        `IfFileExists "$INSTDIR\\${HRMA_IMZA}" bizim_kurulum yabanci_dizin`
        satırı `Goto bizim_kurulum` yapıldığında bekçi YEŞİL kalıyordu, çünkü
        aynı dizgi KURULUM tarafındaki `HrmaDizinKullanilabilirMi` içinde de
        geçiyor. Artık her iddia kendi bölümünün gövdesinde aranır.
        """
        i = kod.find(basi)
        assert i >= 0, f'{basi!r} bölümü bulunamadı'
        j = kod.find('SectionEnd', i)
        assert j > i, f'{basi!r} bölümünün SectionEnd`i yok'
        return kod[i:j]

    def test_kaldirma_kurulum_imzasini_ARIYOR(self):
        kod = self._kod()
        kaldirma = self._bolum(kod, 'Section "Uninstall"')
        assert 'IfFileExists "$INSTDIR\\${HRMA_IMZA}"' in kaldirma, (
            'KALDIRMA bölümü, dizinin bize ait olduğunu doğrulayan imzayı '
            f'aramıyor:\n{kaldirma[:600]}')
        # Dallanma iddiası: imza VARSA/YOKSA iki ayrı yol koşmalı. Yalnız
        # dizginin varlığını aramak yetmez — `Goto bizim_kurulum` mutasyonu
        # dizgiyi bırakıp dallanmayı öldürüyordu (Fable-D17 ölçümü).
        assert re.search(
            r'IfFileExists\s+"\$INSTDIR\\\$\{HRMA_IMZA\}"\s+bizim_kurulum\s+yabanci_dizin',
            kaldirma), (
            'kaldırmanın imza dallanması yok (imza VAR -> bizim_kurulum, YOK '
            f'-> yabanci_dizin):\n{kaldirma[:600]}')
        for etiket in ('bizim_kurulum:', 'yabanci_dizin:'):
            assert etiket in kaldirma, (
                f'kaldırma bölümünde {etiket!r} dalı yok — imza sonucu ne '
                'olursa olsun aynı iş yapılıyor demektir')
        assert re.search(r'RMDir\s+"\$INSTDIR"\s*(;.*)?$', kaldirma, re.M), (
            'kök dizin için özyinelemeli OLMAYAN `RMDir "$INSTDIR"` yok — '
            'boş kalmayan bir dizin sessizce silinmemeli')

    def test_kurulum_bolumu_SILMEDEN_ONCE_dogrulama_cagiriyor(self):
        r"""ÖH D19 — Fable-D17 P10B3-23 ŞARTI (2).

        `.onVerifyInstDir` yalnız dizin sayfası görüldüğünde çağrılır; sessiz
        kurulumda (`/S /D=D:\Projeler`) o sayfa hiç açılmaz. Kurulum bölümü
        ise `RMDir /r "$INSTDIR\app|libs|python"` ile yabancı dizinin altını
        siliyordu. Doğrulama çağrısı KOŞULSUZ silmelerden ÖNCE gelmeli.
        """
        kod = self._kod()
        kurulum = self._bolum(kod, 'Section "HRMA" SecMain')
        i_cagri = kurulum.find('Call HrmaDizinKullanilabilirMi')
        assert i_cagri >= 0, (
            'kurulum bölümü dizin doğrulamasını hiç çağırmıyor — sessiz '
            f'kurulum yolunda yabancı dizin uyarısız siliniyor:\n{kurulum[:600]}')
        silmeler = [m.start() for m in
                    re.finditer(r'RMDir\s+/r\s+"\$INSTDIR\\', kurulum)]
        assert silmeler, 'kurulum bölümünde beklenen RMDir /r yok (adres göçtü)'
        assert i_cagri < min(silmeler), (
            'doğrulama çağrısı ilk `RMDir /r "$INSTDIR..."` SONRASINDA — '
            'silme zaten olmuş olur')
        kuyruk = kurulum[i_cagri:min(silmeler)]
        assert 'Abort' in kuyruk, (
            'doğrulama başarısızken kurulum DURMUYOR (Abort yok) — hüküm '
            f'kazanılmadan siliniyor:\n{kuyruk[:400]}')
        assert '/SD IDOK' in kuyruk, (
            'uyarı kutusunda sessiz-mod varsayılanı (/SD) yok — `/S` ile '
            'kurulum kutuda asılı kalır')

        # --- ÖH D25 / Fable-D19 P10B3-23 ŞARTI — DALLANMA YÖNÜ -------------
        # Yukarıdaki dört iddia "çağrı var / silmeden önce / Abort var /
        # /SD var" diyor ama hiçbiri KOŞULUN YÖNÜNÜ sormuyordu. NSIS'te
        # `StrCmp $R0 "1" <etiket>` = "R0 '1'e EŞİTSE etikete atla"; "1"
        # HrmaDizinKullanilabilirMi'nin KULLANILABİLİR yanıtıdır, yani
        # atlama Abort'un ÜSTÜNDEN yapılır. Karşılaştırma değeri "0"a
        # çevrilirse mantık tam ters döner: kullanılabilir dizin Abort'a
        # düşer, YABANCI dizin ise doğrulamayı atlayıp RMDir /r'lere gider —
        # onarımın kapattığı kusurun ta kendisi. Ölçüldü: bu iddia
        # eklenmeden önce `"1"` -> `"0"` mutasyonu sınıfın 5 testinden
        # HİÇBİRİNİ kırmızıya çeviremiyordu (docs/scofield/raw/OH/D25/
        # altyapi/a2/mutasyon.json, M2).
        izleyen = kurulum[i_cagri:].split('\n')[1]
        m_yon = re.match(r'\s*StrCmp\s+\$R0\s+"1"\s+(\w+)\s*$', izleyen)
        assert m_yon, (
            '`Call HrmaDizinKullanilabilirMi` satırını hemen izleyen satır '
            '`StrCmp $R0 "1" <etiket>` değil — dallanmanın YÖNÜ '
            f'doğrulanamıyor:\n{izleyen!r}')
        etiket = m_yon.group(1)
        i_strcmp = i_cagri + kurulum[i_cagri:].find('StrCmp')
        i_abort = kurulum.find('Abort', i_strcmp)
        assert i_abort > i_strcmp, (
            'StrCmp`den SONRA `Abort` yok — koşul sağlanmadığında kurulum '
            'durmuyor demektir')
        m_etiket = re.search(r'^\s*%s:' % re.escape(etiket), kurulum[i_strcmp:],
                             re.M)
        assert m_etiket, (
            f'`StrCmp` {etiket!r} etiketine atlıyor ama etiket TANIMLI DEĞİL')
        i_etiket = i_strcmp + m_etiket.start()
        assert i_strcmp < i_abort < i_etiket, (
            f'`{etiket}:` tanımı `Abort`tan ÖNCE — "kullanılabilir" dalı '
            'Abort`un üstünden atlamıyor, yani doğrulama hiçbir şeyi '
            f'engellemiyor (StrCmp@{i_strcmp}, Abort@{i_abort}, '
            f'etiket@{i_etiket})')

    def test_kurulum_imzayi_YAZIYOR(self):
        kod = self._kod()
        assert 'FileOpen $0 "$INSTDIR\\${HRMA_IMZA}" w' in kod, (
            'kurulum imza dosyasını yazmıyor — kaldırma hiçbir zaman kendi '
            'dizinini tanıyamaz ve her seferinde yabancı-dizin yoluna düşer')


# ---------------------------------------------------------------------------
# P10B3-01 / P10B3-02 — görsel tur bir kapıya bağlı mı
# ---------------------------------------------------------------------------

class TestGorselTurKapiyaBagli:

    def test_release_gate_turu_cagiriyor(self):
        metin = KAPI_BETIGI.read_text(encoding='utf-8')
        kod = '\n'.join(s for s in metin.split('\n')
                        if not s.lstrip().startswith('#'))
        assert 'tools/browser_harness/run_tour.py' in kod, (
            'yayın kapısı görsel turu çağırmıyor — 3.263 satırlık iskele '
            'yine hiçbir kapıya bağlı değil (P10B3-01)')

    def test_playwright_yoksa_kapi_KAPANIR(self):
        """FAIL-CLOSED: "görsel doğrulayamadım" bir geçiş gerekçesi değildir."""
        metin = KAPI_BETIGI.read_text(encoding='utf-8')
        bolum = _adim_bolumu(metin)
        assert 'import playwright' in bolum, bolum[:400]
        oncesi = bolum[:bolum.find('import playwright')]
        sonrasi = bolum[bolum.find('import playwright'):]
        assert re.search(r'basarisiz "playwright kurulu değil', sonrasi), (
            'playwright yokken adım `atlandi` diyor ya da sessiz geçiyor — '
            f'fail-closed değil:\n{sonrasi[:500]}')
        assert 'atlandi "playwright' not in sonrasi, sonrasi[:400]
        assert oncesi is not None

    def test_kapinin_bastigi_rapor_adi_RAPOR_ADI_ile_AYNI(self):
        """ÖH D19 — Fable-D17 P10B3-01 ŞARTI (TEK KAYNAK).

        Ölçüldü: kapı kırmızıda `rapor: $TUR_DIZINI/rapor.json` basıyordu,
        `run_tour.py` ise raporu `RAPOR_ADI = 'tour_report.json'` adıyla
        yazıyor — kullanıcı gösterilen yolu bulamazdı. Ad iki yerde
        yazılmamalı: kapı üreticiden okumalı.
        """
        from tools.browser_harness.run_tour import RAPOR_ADI
        metin = KAPI_BETIGI.read_text(encoding='utf-8')
        kod = '\n'.join(x for x in metin.split('\n')
                        if not x.lstrip().startswith('#'))
        bolum = _adim_bolumu(kod)
        basilan = set(re.findall(r'rapor: \$TUR_DIZINI/([^\s,)"]+)', bolum))
        assert basilan, f'kapı hiçbir rapor yolu basmıyor:\n{bolum[:600]}'
        assert basilan == {'$TUR_RAPOR_ADI'}, (
            f'kapı rapor adını SABİT basıyor ({sorted(basilan)}) — üreticinin '
            f'adı {RAPOR_ADI!r}; ad tek kaynaktan okunmalı')
        assert 'from tools.browser_harness.run_tour import RAPOR_ADI' in bolum, (
            'kapı rapor adını üreticiden okumuyor (RAPOR_ADI ithali yok) — '
            f'yol yine ayrışabilir:\n{bolum[:600]}')
        # Kaynaktan okunan ad gerçekten üreticinin adı olmalı.
        r = subprocess.run(
            [sys.executable, '-c',
             'from tools.browser_harness.run_tour import RAPOR_ADI; '
             'print(RAPOR_ADI)'],
            cwd=str(DEPO), capture_output=True, text=True, timeout=180)
        assert r.returncode == 0 and r.stdout.strip().splitlines()[-1] == RAPOR_ADI, (
            'kapının kullandığı okuma komutu çalışmıyor — kapı adı '
            f'okuyamaz ve FAIL-CLOSED kapanır:\n{r.stdout}\n{r.stderr}')

    def test_rapor_adi_okunamazsa_kapi_KAPANIR(self):
        """FAIL-CLOSED: ad okunamıyorsa uydurma bir yol basılmaz."""
        metin = KAPI_BETIGI.read_text(encoding='utf-8')
        kod = '\n'.join(x for x in metin.split('\n')
                        if not x.lstrip().startswith('#'))
        bolum = _adim_bolumu(kod)
        i = bolum.find('TUR_RAPOR_ADI=')
        assert i >= 0, bolum[:400]
        kuyruk = bolum[i:i + 800]
        assert re.search(r'if \[ -z "\$TUR_RAPOR_ADI" \]', kuyruk), (
            f'ad boş gelirse kapı bir şey demiyor:\n{kuyruk[:400]}')
        assert 'basarisiz "görsel tur rapor adı okunamadı' in kuyruk, (
            f'ad okunamayınca kapı KAPANMIYOR:\n{kuyruk[:400]}')

    def test_kapi_adimlari_1den_Ne_kesintisiz_ve_payda_KENDI_sayisini_soyluyor(self):
        """Adım sayısı ELLE yazılmaz; kapının kendi beyanıyla tutarlılık ölçülür.

        ÖH D28 / altyapi (OH-D27-04): eskiden ``range(1, 10)`` ve payda
        ``{'9'}`` diye SABİT SAYI mandalıydı; 10. adım eklenince mandal
        meşru bir yüzey değişikliğinde kırılıyor ve tek çare sayıyı
        yükseltmek oluyordu — yani mandal hiçbir şey ölçmüyordu. Ölçülen
        şey artık ilişkidir: numaralar 1..N kesintisiz mi, ve her başlığın
        yazdığı payda GERÇEK adım sayısına eşit mi. Yeni adım eklemek
        serbest; paydasını güncellemeden eklemek KIRMIZI.
        """
        basliklar = re.findall(r'^baslik "(\d+)/(\d+)\s',
                               KAPI_BETIGI.read_text(encoding='utf-8'), re.M)
        assert basliklar, 'kapıda hiç `baslik "N/P ..."` adımı yok'
        numaralar = [int(a) for a, _ in basliklar]
        paydalar = {int(b) for _, b in basliklar}
        assert numaralar == list(range(1, len(basliklar) + 1)), basliklar
        assert paydalar == {len(basliklar)}, (
            f'{len(basliklar)} adım var ama başlıklar {sorted(paydalar)} '
            f'paydasını yazıyor', basliklar)


# ---------------------------------------------------------------------------
# P10B3-09 — ISA tablosu tek kaynak (ürün yüzündeki kopyalar ayrışmasın)
# ---------------------------------------------------------------------------

def test_advanced_html_ISA_tablosu_constants_ile_AYNI():
    """Tarayıcı kopyası merkezden ayrışırsa 47 km'de basınç %30 sapıyordu.

    D15'te iki kopya da `hrma.constants`a bağlandı; bu bekçi ayrışmayı
    ölçer (JS tablosu elle yazılmış bir kopya olduğu için drift mümkündür).
    """
    from hrma import constants as C
    html = (DEPO / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    i = html.find('ISA_LAYERS_JS = [')
    assert i > 0, 'advanced.html içinde ISA_LAYERS_JS tablosu yok'
    blok = html[i:html.find('];', i)]
    js = []
    for satir in re.findall(r'\[([^\]]+)\]', blok):
        try:
            js.append(tuple(float(x) for x in satir.split(',')))
        except ValueError:                          # pragma: no cover
            pass
    py = [tuple(float(x) for x in kat) for kat in C.ISA_LAYERS]
    assert len(js) == len(py), (
        f'JS tablosunda {len(js)} katman, constants`ta {len(py)}')
    for a, b in zip(py, js):
        for x, y in zip(a, b):
            assert abs(x - y) <= 1e-9 * max(1.0, abs(x)), (
                f'ISA katmanı ayrıştı: constants {a} ⟷ advanced.html {b}')
