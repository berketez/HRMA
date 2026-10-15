"""Faz 4B yayın zinciri ve yönetişim bekçi testleri (E1-E5).

Kapsanan bulgular
-----------------
E1/E2 — v2.6.25 yayın kazası. GitHub zaman damgaları (UTC):

    22:46:25  DMG + EXE üretildi
    23:23:16  commit d908ae7        <-- ikili kaynaktan 36 dk 51 sn ÖNCE
    23:23:50  CI başladı
    23:30:44  SÜRÜM YAYINLANDI      <-- CI hâlâ koşuyordu
    23:38:09  CI yeşil bitti        <-- yayından 7 dk 25 sn SONRA

    Mekanizma ``KAPIYI_ATLA=1`` idi: 288 satırlık kapının TAMAMINI
    atlıyordu — taslak kısıtı yok, gerekçe yok, kaydı yok.

E3  — ``.github/workflows/`` altında yalnız ``tests.yml`` vardı; yayın
      sırasını zorlayan hiçbir otomasyon yoktu.
E4  — ``docs/VALIDATION_STATUS.md`` bayattı: kaldırılmış olan
      ``hybrid | thrust | main`` satırı belgede duruyordu, README ise
      bloğa "always-current" diyordu.
E5  — Yönetişim dosyalarının yedisi de yoktu.

Test felsefesi
--------------
``publish_release.sh`` kapıları GERÇEKTEN ÇALIŞTIRILARAK sınanır: tmp_path
içinde sahte bir depo kurulur, ``gh`` ve ``release_gate.sh`` yerine çağrıyı
diske kaydeden vekiller konur. Böylece test betiğin metnine değil
DAVRANIŞINA bakar — hiçbir şey yayınlanmaz, ağa çıkılmaz.

``release_gate.sh``ın 3/7 ve 4/7 adımları YAPISAL olarak sınanır (gerçek
kapı tam test takımını ve canlı sunucuyu kaldırır, ~20 dk). Yapısal
demek "grep" demek değil: betik ``baslik "N/7"`` sınırlarından bölünür ve
her adımın gövdesi ayrı ayrı denetlenir — CI adımının atlama bayrağını
GÖRMEDİĞİ böyle kanıtlanır.
"""

import glob
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

# NOT: PyYAML BİLEREK modül düzeyinde import EDİLMİYOR. requirements.txt ve
# requirements-dev.txt'in ikisinde de yok (CI tam olarak o iki dosyayı kurar),
# dolayısıyla `import yaml` bu dosyanın CI'da hiç TOPLANAMAMASINA yol açardı —
# yani yayın zincirini koruyan 25 testin sessizce kaybolmasına. Derin YAML
# denetimleri pytest.importorskip ile isteğe bağlıdır; her testin ASIL
# sözleşmesi ayrıca ham metin üzerinden, ayrıştırıcısız ölçülür.

DEPO = Path(__file__).resolve().parents[1]

ISAKISI_DIZINI = DEPO / ".github" / "workflows"
YAYIN_BETIGI = DEPO / "packaging" / "publish_release.sh"
KAPI_BETIGI = DEPO / "packaging" / "release_gate.sh"
DURUM_BELGESI = DEPO / "docs" / "VALIDATION_STATUS.md"

# Sahte depoda kullanılan sürüm: gerçek bir sürümle karışmasın diye
# kasten imkânsız bir numara.
SAHTE_SURUM = "9.9.9"

# CONTRIBUTING.md'nin "bunları commit etme" diye andığı yapı çıktısı
# dizinleri. .gitignore'da oldukları için temiz bir ağaçta YOKTURLAR;
# yol-varlık denetiminin dışında kalmaları gerekir.
YAPI_CIKTISI_DIZINLERI = {"dist/", "packaging/mac/", "packaging/win/"}


# ---------------------------------------------------------------------------
# E1/E2 — publish_release.sh kapıları (davranışsal)
# ---------------------------------------------------------------------------

def _yayin_tezgahi(tmp_path, kapi_cikis=0):
    """publish_release.sh'i gerçekten koşturabilmek için sahte depo kurar.

    Betik ``SRC``yi kendi konumundan türetir
    (``dirname "$0"/..``), dolayısıyla betiği ``<kök>/packaging/`` altına
    kopyalamak onu tümüyle bu sahte ağaca hapseder: gerçek depo okunmaz,
    gerçek ``dist/`` aranmaz.

    Döndürür: (kök, kayıt_dizini, bin_dizini)
    """
    kok = tmp_path / "depo"
    (kok / "packaging").mkdir(parents=True)
    (kok / "hrma").mkdir()
    (kok / "dist").mkdir()
    kayit = tmp_path / "kayit"
    kayit.mkdir()

    shutil.copy(YAYIN_BETIGI, kok / "packaging" / "publish_release.sh")

    (kok / "hrma" / "__init__.py").write_text(
        f'__version__ = "{SAHTE_SURUM}"\n', encoding="utf-8")
    (kok / "dist" / f"HRMA-Setup-{SAHTE_SURUM}-macOS.dmg").write_bytes(b"sahte dmg")
    (kok / "dist" / f"HRMA-Setup-{SAHTE_SURUM}.exe").write_bytes(b"sahte exe")
    # Betik iki dil imini de arar; yoksa daha kapıya varmadan durur.
    (kok / "packaging" / f"release_notes_v{SAHTE_SURUM}.md").write_text(
        "<!--HRMA-LANG:en-->\nEnglish notes\n"
        "<!--HRMA-LANG:tr-->\nTürkçe notlar\n", encoding="utf-8")
    (kok / "README.md").write_text(
        f"HRMA-Setup-{SAHTE_SURUM}-macOS.dmg\n", encoding="utf-8")

    # Kapı vekili: çağrıldığını kaydeder, istenen kodla çıkar.
    kapi = kok / "packaging" / "release_gate.sh"
    kapi.write_text(
        "#!/bin/bash\n"
        f'echo calisti >> "{kayit}/kapi.txt"\n'
        f"exit {kapi_cikis}\n", encoding="utf-8")
    kapi.chmod(0o755)

    # gh vekili: YAYIN gerçekten denenirse argümanlarını diske yazar.
    # Dosyanın VARLIĞI "yayın denendi" demektir — testlerin çoğu tam
    # olarak bunun OLMADIĞINI kanıtlar.
    bin_dizin = tmp_path / "bin"
    bin_dizin.mkdir()
    gh = bin_dizin / "gh"
    gh.write_text(
        "#!/bin/bash\n"
        f'printf "%s\\n" "$@" > "{kayit}/gh.txt"\n'
        "exit 0\n", encoding="utf-8")
    gh.chmod(0o755)

    return kok, kayit, bin_dizin


def _kostur(kok, bin_dizin, **cevre):
    ortam = dict(os.environ)
    ortam["PATH"] = f"{bin_dizin}{os.pathsep}{ortam['PATH']}"
    # Kalıtım kazası olmasın: kapı değişkenleri her koşuda açıkça verilir.
    for anahtar in ("TASLAK", "KAPIYI_ATLA", "KAPIYI_ATLA_GEREKCE"):
        ortam.pop(anahtar, None)
    ortam.update({anahtar: str(deger) for anahtar, deger in cevre.items()})
    return subprocess.run(
        ["bash", str(kok / "packaging" / "publish_release.sh"), "yedek not"],
        capture_output=True, text=True, timeout=180, env=ortam, cwd=str(kok))


def _gh_argumanlari(kayit):
    yol = kayit / "gh.txt"
    if not yol.exists():
        return None
    return yol.read_text(encoding="utf-8").splitlines()


def test_betikler_sozdizimi_gecerli():
    """Kapı ve yayın betikleri bash sözdizimi denetiminden geçmeli.

    macOS'ta bash 3.2 var; betikte bilinçli olarak bash 3.2 uyumlu
    ``${dizi[@]+"${dizi[@]}"}`` biçimi kullanılıyor. Sözdizimi hatası
    yayın anında, en kötü zamanda ortaya çıkar.
    """
    for betik in (YAYIN_BETIGI, KAPI_BETIGI):
        sonuc = subprocess.run(["bash", "-n", str(betik)],
                               capture_output=True, text=True, timeout=60)
        assert sonuc.returncode == 0, f"{betik.name}: {sonuc.stderr}"


def test_kapi_atlama_herkese_acik_surumu_reddeder(tmp_path):
    """E2(a): KAPIYI_ATLA yalnız taslakta geçerli — asıl düzeltme budur.

    v2.6.25 tam olarak böyle çıktı: kapı atlandı ve sürüm HERKESE AÇIK
    yayınlandı. Artık betik burada durmalı; ne kapı ne de gh çağrılmalı.
    """
    kok, kayit, bin_dizin = _yayin_tezgahi(tmp_path)
    sonuc = _kostur(kok, bin_dizin, KAPIYI_ATLA="1",
                    KAPIYI_ATLA_GEREKCE="yeterince uzun ve anlamli bir gerekce")

    assert sonuc.returncode != 0, "herkese açık sürüm kapı atlanarak çıktı"
    assert _gh_argumanlari(kayit) is None, "gh çağrıldı — sürüm YAYINLANDI"
    assert not (kayit / "kapi.txt").exists()
    assert "TASLAK" in sonuc.stdout


def test_taslak_atlamasi_gerekce_ister(tmp_path):
    """E2(a): gerekçe zorunlu — "1" yazıp geçilemez."""
    kok, kayit, bin_dizin = _yayin_tezgahi(tmp_path)
    sonuc = _kostur(kok, bin_dizin, TASLAK="1", KAPIYI_ATLA="1")

    assert sonuc.returncode != 0, "gerekçesiz atlama kabul edildi"
    assert _gh_argumanlari(kayit) is None
    assert "GEREKCE" in sonuc.stdout


def test_taslak_atlamasi_kisa_gerekceyi_reddeder(tmp_path):
    """Gerekçe en az 20 karakter: "ok" ya da "1" beyan sayılmaz."""
    kok, kayit, bin_dizin = _yayin_tezgahi(tmp_path)
    sonuc = _kostur(kok, bin_dizin, TASLAK="1", KAPIYI_ATLA="1",
                    KAPIYI_ATLA_GEREKCE="1")

    assert sonuc.returncode != 0, "tek karakterlik gerekçe kabul edildi"
    assert _gh_argumanlari(kayit) is None


def test_taslak_atlamasi_gerekceyi_deftere_ve_surum_notuna_yazar(tmp_path):
    """E2(a): atlama iki yere kalıcı yazılır — defter ve taslağın gövdesi.

    İkincisi önemli: taslağı sonradan GitHub arayüzünden yayına çeviren
    kişi bu betiği hiç çalıştırmaz. Uyarı sürüm notunun EN BAŞINDA
    değilse, o kişi kapının atlandığını hiç öğrenemez.
    """
    gerekce = "imza makinesi cevrimdisi, yalniz ic deneme taslagi"
    kok, kayit, bin_dizin = _yayin_tezgahi(tmp_path)
    sonuc = _kostur(kok, bin_dizin, TASLAK="1", KAPIYI_ATLA="1",
                    KAPIYI_ATLA_GEREKCE=gerekce)

    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    # Kapı gerçekten atlandı (vekil hiç çağrılmadı).
    assert not (kayit / "kapi.txt").exists()

    defter = kok / "packaging" / "release_gate_bypass.log"
    assert defter.exists(), "atlama defteri yazılmadı"
    defter_metni = defter.read_text(encoding="utf-8")
    assert gerekce in defter_metni
    assert SAHTE_SURUM in defter_metni

    argumanlar = _gh_argumanlari(kayit)
    assert argumanlar is not None, "taslak yayınlanmadı"
    assert "--draft" in argumanlar, "TASLAK=1 olduğu hâlde --draft geçilmedi"

    # Sürüm notu gövdesinin EN BAŞI uyarı olmalı.
    konum = argumanlar.index("--notes-file")
    not_govdesi = Path(argumanlar[konum + 1]).read_text(encoding="utf-8")
    ilk_satir = not_govdesi.splitlines()[0]
    assert "YAYIN KAPISI ATLANDI" in ilk_satir, ilk_satir
    assert gerekce in not_govdesi


def test_kapi_kirmizi_ise_yayin_yok(tmp_path):
    """E2: atlama yoksa kapı koşar ve kırmızı kapı yayını durdurur."""
    kok, kayit, bin_dizin = _yayin_tezgahi(tmp_path, kapi_cikis=1)
    sonuc = _kostur(kok, bin_dizin)

    assert sonuc.returncode != 0, "kapı kırmızıyken sürüm yayınlandı"
    assert (kayit / "kapi.txt").exists(), "kapı hiç çağrılmadı"
    assert _gh_argumanlari(kayit) is None, "gh çağrıldı — sürüm YAYINLANDI"


def test_kapi_yesil_ise_herkese_acik_yayin_olur(tmp_path):
    """Kapı düzgün çalışırsa normal yayın yolu tıkanmamalı.

    Bekçi testinin ikinci yarısı: kapıyı sıkılaştırmak, geçerli yayını
    imkânsız hâle getirmemeli.
    """
    kok, kayit, bin_dizin = _yayin_tezgahi(tmp_path, kapi_cikis=0)
    sonuc = _kostur(kok, bin_dizin)

    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert (kayit / "kapi.txt").exists(), "kapı koşmadan yayın yapıldı"
    argumanlar = _gh_argumanlari(kayit)
    assert argumanlar is not None, "kapı yeşilken yayın yapılmadı"
    assert argumanlar[:2] == ["release", "create"]
    assert f"v{SAHTE_SURUM}" in argumanlar
    assert "--draft" not in argumanlar


# ---------------------------------------------------------------------------
# E1(b)/E1(c) — release_gate.sh adımları (yapısal)
# ---------------------------------------------------------------------------

def _kapi_bolumleri():
    """Kapı betiğini ``baslik "N/P ..."`` sınırlarından bölümlere ayırır.

    2026-08-04: kapıya 8. adım (paket içerik manifesti + boyut sapması)
    eklendi; ayrıştırıcı /7'den /8'e güncellendi.
    2026-09-02 (ÖH D17 / altyapi, defter P10B3-01): 9. adım (görsel tur —
    ``tools/browser_harness/run_tour.py``) eklendi; ayrıştırıcı /8'den /9'a
    güncellendi. İDDİA DEĞİŞMEDİ ("kapının her adımı ayrıştırılabilir ve
    atlama bayrağını görmez"), yalnız adım sayısı arttı.
    2026-09-08 (ÖH D28 / altyapi, defter OH-D27-04): 10. adım (iddia dili
    kapısı — ``tools/iddia_lint.py --check``) eklendi. Bu sefer ayrıştırıcı
    paydayı ARTIK SABİT YAZMIYOR: desen üç dalgada üst üste elle güncellendi
    ve her seferinde "sayıyı yükselt" dışında bir seçenek bırakmadı. Payda
    da yakalanır ve ``test_kapi_her_adimi_ayristirilabiliyor`` beyanın
    gerçek adım sayısına eşit olduğunu ölçer.
    """
    metin = KAPI_BETIGI.read_text(encoding="utf-8")
    parcalar = re.split(r'^baslik "(\d+)/(\d+)\s+([^"]*)"', metin, flags=re.M)
    bolumler = {}
    for indeks in range(1, len(parcalar), 4):
        bolumler[int(parcalar[indeks])] = parcalar[indeks + 3]
    return bolumler


def _kapi_paydalari():
    """Başlıkların yazdığı payda kümesi (``N/P`` içindeki P)."""
    metin = KAPI_BETIGI.read_text(encoding="utf-8")
    return {int(p) for _n, p in
            re.findall(r'^baslik "(\d+)/(\d+)\s', metin, flags=re.M)}


def _kod_satirlari(govde):
    """Yorum satırlarını atar, çalışan kabuk kodunu döndürür.

    Gerekli çünkü kapı betiği neyin NEDEN değiştiğini gövdesinde
    anlatıyor: 4/7 adımının yorum bloğu "eskiden HIZLI=1 ile
    atlanabiliyordu" diye geçmişi yazar. O cümle koda bakan bir denetimi
    yanıltmamalı — ölçülmek istenen şey, atlama bayrağının ÇALIŞAN kodda
    geçmemesi.
    """
    return "\n".join(satir for satir in govde.splitlines()
                     if not satir.lstrip().startswith("#"))


def test_kapi_her_adimi_ayristirilabiliyor():
    """Adımlar 1..N kesintisiz VE başlıkların paydası N'e eşit.

    ÖH D28 / altyapi (OH-D27-04): eskiden ``range(1, 10)`` diye sabit
    sayıydı. Sabit sayı meşru bir yüzey büyümesinde kırılır ve tek çözümü
    sayıyı yükseltmektir — yani hiçbir şey ölçmez. Ölçülen artık ilişkidir:
    numaralar kesintisiz mi ve kapı kendi adım sayısını doğru mu söylüyor.
    """
    bolumler = _kapi_bolumleri()
    assert bolumler, 'kapıda hiç adım bulunamadı'
    assert sorted(bolumler) == list(range(1, len(bolumler) + 1)), sorted(bolumler)
    assert _kapi_paydalari() == {len(bolumler)}, (
        f'{len(bolumler)} adım var ama başlıklar '
        f'{sorted(_kapi_paydalari())} paydasını yazıyor')


def test_ci_kontrolu_hicbir_atlama_bayragi_gormez():
    """E1(c): CI kontrolü ATLANAMAZ.

    Eskiden CI kontrolü tam test takımıyla AYNI bayrağın (HIZLI) altındaydı.
    Oysa maliyetleri taban tabana zıt: tam takım ~20 dk, CI kontrolü tek
    API çağrısı. Aynı bayrağa bağlamak, "hızlı geçeyim" diyen kişiye
    farkında olmadan projenin en güçlü kanıtını atlatıyordu.

    Bu test atlama bayrağının YALNIZ 5/7 (tam takım) gövdesinde
    geçebileceğini sınar — CI adımının onu görmediğini kanıtlar.
    """
    for numara, govde in _kapi_bolumleri().items():
        if numara == 5:
            continue
        kod = _kod_satirlari(govde)
        for bayrak in ("TAKIMI_ATLA", "HIZLI"):
            assert bayrak not in kod, (
                f"{numara}. adım '{bayrak}' atlama bayrağını görüyor — "
                f"atlanabilir hâle gelmiş")

    # Karşı yön: bayrak 5/7'de GERÇEKTEN duruyor olmalı. Yoksa test,
    # bayrak tümden silindiğinde de yeşil kalır ve hiçbir şey ölçmez.
    assert "TAKIMI_ATLA" in _kod_satirlari(_kapi_bolumleri()[5])


def test_ci_kontrolu_bu_shanin_butun_kosularini_sayar():
    """E1(c): tamamlanmamış ya da başka SHA'ya ait koşu yayını durdurmalı.

    v2.6.25 yayın anında CI DEVAM EDİYORDU. Tek koşuya (``--limit 1``)
    bakmak bunu yakalamaz: depoda iki iş akışı var, biri bitmiş biri
    koşuyorken "en son bitene" bakmak yeşil der.
    """
    govde = _kapi_bolumleri()[4]

    assert "gh run list" in govde
    assert "--limit 1 " not in govde and "--limit 1\n" not in govde, (
        "CI kontrolü hâlâ tek koşuya bakıyor")

    # Tamamlanmamış koşu -> KALDI
    assert 'if [ "$DURUM" != "completed" ]' in govde
    assert re.search(r'!= "completed"[^\n]*\n\s*basarisiz', govde), (
        "tamamlanmamış koşu için basarisiz dalı yok")

    # SHA bağı: koşu tam olarak yayınlanacak ağacı temsil etmeli.
    assert "headSha" in govde
    assert '"$SHA" != "$YEREL"' in govde

    # Hiç koşu yoksa yeşil sayılmamalı.
    assert re.search(r'if \[ -z "\$KOSULAR" \][^\n]*\n\s*basarisiz', govde), (
        "CI koşusu hiç yokken kapı geçiyor")

    # Asıl kanıt 'tests' iş akışının yeşili.
    assert 'TESTS_YESIL' in govde


def test_yapi_commit_zaman_sirasi_kapisi():
    """E1(b): artefakt, temsil ettiği commit'ten ÖNCE üretilmişse KALDI.

    v2.6.25'te DMG+EXE commit'ten 36 dk 51 sn önce üretilmişti; indirilen
    kurulum paketi sürüm notunun anlattığı düzeltmelerin hiçbirini
    içermiyordu ve bunu hiçbir kontrol yakalamadı.
    """
    govde = _kapi_bolumleri()[3]

    # Commit zamanı COMMITTER tarihinden (%ct) okunmalı: rebase/amend
    # sonrası author tarihi eski kalabilir.
    assert "%ct" in govde, "commit zamanı committer tarihinden okunmuyor"
    assert "getmtime" in govde, "artefakt değiştirilme zamanı ölçülmüyor"

    # Karşılaştırma ve iki dal: sonra -> GEÇTİ, önce -> KALDI.
    assert '"$ARTEFAKT_EPOCH" -ge "$COMMIT_EPOCH"' in govde
    assert re.search(r"ÖNCE üretilmiş", govde), "erken yapı için KALDI metni yok"

    # Artefakt yoksa sessizce geçilmemeli.
    assert re.search(r'if \[ ! -f "\$ARTEFAKT" \][^\n]*\n\s*basarisiz', govde), (
        "artefakt yokken kapı geçiyor")

    # Hem DMG hem EXE denetlenmeli.
    assert "$DMG_YOL" in govde and "$EXE_YOL" in govde


# ---------------------------------------------------------------------------
# E3 — release iş akışı
# ---------------------------------------------------------------------------

def _is_akisi_yukle(ad):
    """İş akışını ayrıştırır. PyYAML ZORUNLUDUR — atlama yolu yoktur.

    ÖH defter **OH-B3-05**: burada eskiden ``pytest.importorskip("yaml")``
    duruyordu. Gerekçesi (üstteki modül notu) ölçüldüğü gün doğruydu:
    PyYAML hiçbir requirements dosyasında yoktu. O ölçüm ARTIK GEÇERSİZ —
    ``requirements-dev.txt`` PyYAML'i zorunlu bildiriyor ve ``tests.yml``
    kurulumu ``import yaml`` ile doğruluyor (bekçi:
    :func:`test_yonetisim_bekcilerinin_bagimliligi_bildirilmis`). Kalan
    ``importorskip`` bu yüzden bağımlılık kapısı değil, E3 iş akışı
    bekçilerini SESSİZLEŞTİRME yoluydu: PyYAML kurulumu bir gün kırılsa
    kapı kırmızı vermek yerine testleri atlardı.

    İthal MODÜL düzeyine ÇIKARILMAZ (üstteki not orada hâlâ geçerli:
    toplama anında kırılırsa dosyanın 25 testi birden junit'te tek satıra
    düşer). Fonksiyon düzeyinde düz ithal, kırıldığında YALNIZ bu testleri
    ve DÜRÜSTÇE kırmızı yapar.
    """
    import yaml

    veri = yaml.safe_load((ISAKISI_DIZINI / ad).read_text(encoding="utf-8"))
    # PyYAML, YAML 1.1 uyarınca çıplak ``on:`` anahtarını True'ya çevirir.
    if True in veri and "on" not in veri:
        veri["on"] = veri.pop(True)
    return veri


def test_release_is_akisi_dosyasi_var():
    """E3: yayın iş akışının VARLIĞI — ayrıştırıcı gerektirmez."""
    dosyalar = {yol.name for yol in ISAKISI_DIZINI.glob("*.yml")}
    assert dosyalar >= {"tests.yml", "release.yml"}, (
        f"release iş akışı yok — E3 açık (bulunan: {sorted(dosyalar)})")


def test_is_akisi_dosyalari_gecerli_yaml():
    """E3: bozuk bir iş akışı SESSİZCE koşmaz — GitHub hiç koşu göstermez.

    "Bu commit için CI koşusu yok" tam olarak yayın kapısının yayına izin
    vermediği durumdur; bozuk YAML'ı burada yakalamak gerekir.
    """
    for dosya in sorted(ISAKISI_DIZINI.glob("*.yml")):
        veri = _is_akisi_yukle(dosya.name)
        assert veri.get("jobs"), f"{dosya.name}: jobs yok"
        assert "on" in veri, f"{dosya.name}: tetikleyici yok"


def test_release_is_akisi_sirayi_zorlar():
    """E3: testler yeşil olmadan taslak sürüm açılamaz.

    2026-08-04: release.yml etiket-tetiklemeli yayın hattına dönüştü
    (7 iş: surum-baglantisi, testler, ci-durumu, mac-paket, win-paket,
    taslak-yayin, yayin-denetimi). Eski bekçi literal ``needs: test``
    metnini arıyordu — eski yapıyı kilitliyordu. Değişmez aynı kaldı:
    yayın (taslak) işi, test ve CI işleri YEŞİL olmadan koşamaz; bunu
    artık yapıya değil bağımlılık grafiğine bakarak sınıyoruz.
    """
    metin = (ISAKISI_DIZINI / "release.yml").read_text(encoding="utf-8")
    assert re.search(r"^\s*tags:\s*$", metin, re.M), (
        "v* etiketi zinciri başlatmıyor")

    veri = _is_akisi_yukle("release.yml")
    isler = veri["jobs"]
    for ad in ("surum-baglantisi", "testler", "ci-durumu",
               "taslak-yayin", "yayin-denetimi"):
        assert ad in isler, f"release iş akışında '{ad}' işi yok"

    # Çekirdek sözleşme: taslak sürümü açan iş, test + CI işlerine
    # bağımlı olmak ZORUNDA. `needs` düşerse "test yeşil olmadan sürüm
    # yayımlandı" durumu geri gelir.
    taslak_needs = isler["taslak-yayin"].get("needs") or []
    if isinstance(taslak_needs, str):
        taslak_needs = [taslak_needs]
    for on_kosul in ("testler", "ci-durumu", "surum-baglantisi"):
        assert on_kosul in taslak_needs, (
            f"taslak-yayin '{on_kosul}' işine bağımlı değil — "
            f"sıra zorlanmıyor (needs={taslak_needs})")

    # Eski yapıda sıra 'surum-baglantisi needs: test' ile kuruluyordu;
    # yeni hatta surum-baglantisi bağımsız hızlı bir ön kontrol, sıra
    # yukarıdaki taslak-yayin bağımlılıklarıyla zorlanıyor.
    assert "tags" in (veri["on"].get("push") or {})


def test_yayin_denetimi_zaman_sirasini_olcer():
    """E3/E1: yayın olduysa GitHub kayıtlarından sıra yeniden ölçülmeli.

    Üç ölçüm de ham metin üzerinden aranır; ayrıştırıcı gerekmez.
    """
    metin = (ISAKISI_DIZINI / "release.yml").read_text(encoding="utf-8")

    assert "yayin-denetimi:" in metin
    assert "github.event_name == 'release'" in metin, (
        "yayın denetimi release olayına bağlı değil")

    # (a) bu tam SHA için 'tests' yeşil mi
    assert "head_sha=" in metin and "conclusion" in metin
    # (b) CI yayından ÖNCE mi bitti (v2.6.25: yayın CI'dan 7 dk 25 sn önce)
    assert "published_at" in metin
    # (c) her artefakt commit'ten SONRA mı yüklendi (v2.6.25: 36 dk 51 sn önce)
    assert "created_at" in metin and "assets" in metin


def test_is_akisi_action_surumleri_acik():
    """Kullanılan action'lar resmî ve sürümü açıkça yazılmış olmalı.

    ``@main`` ya da sürümsüz bir referans, yayın zincirinin altındaki
    zemini üçüncü tarafın istediği an değiştirmesine izin verir.
    """
    desen = re.compile(r"^\s*-?\s*uses:\s*(\S+)", re.M)
    for dosya in sorted(ISAKISI_DIZINI.glob("*.yml")):
        metin = dosya.read_text(encoding="utf-8")
        kullanimlar = desen.findall(metin)
        assert kullanimlar, f"{dosya.name}: hiç action kullanılmıyor"
        for kullanim in kullanimlar:
            assert re.fullmatch(r"actions/[a-z0-9-]+@v\d+", kullanim), (
                f"{dosya.name}: '{kullanim}' resmî+sürümlü biçimde değil")


# ---------------------------------------------------------------------------
# H5-2 / H5-4 (Faz 5) — CI'da SESSİZCE atlanan bekçiler
# ---------------------------------------------------------------------------

#: `step-export` işinin koşturması ŞART olan ÇEKİRDEK STEP/CAD dosyaları.
#: Bunlar Faz 4'ün A1 (STL/DXF 1000× birim hatası), A4 (NaN geometriden katı
#: cisim), A8 (katı cidarı) ve A11 (tank geometrisi) bulgularının bekçileridir;
#: 3 Ağustos 2026'da ÖLÇÜLMÜŞ çapadır ve listeden düşemez.
#:
#: DİKKAT — bu tuple artık "işin koşturduğu dosyaların listesi" DEĞİLDİR.
#: 3 Ağustos'tan 17 Ağustos'a kadar öyleydi ve tam olarak o yüzden ÇÜRÜDÜ:
#: iş akışına üç dosya daha eklendi (parti 31 / T2-1), bu beşli sabit kaldı ve
#: bekçi "beş dosya koşuyor mu?" diye sormaya devam etti — sekiz dosyanın
#: üçü hakkında hiçbir şey sınanmadı (defter P13B1-08, ÖH FAZ D / D1).
#: Koşan liste artık `_is_akisindan_step_dosyalari()` ile TÜRETİLİR.
STEP_TEST_CEKIRDEGI = (
    "tests/test_step_import.py",
    "tests/test_tank_step_units.py",
    "tests/test_faz4_export_geometri.py",
    "tests/test_faz4_app_export.py",
    "tests/test_export_generators.py",
)

#: 17 Ağustos 2026 ölçümü (parti 31 / T2-1): `step-export` işi SEKİZ dosya
#: koşuyor (çekirdek beşli + test_step_durustluk_kapisi + test_faz5_cizim_birim
#: + test_faz6_sivi). Türetilen küme bunun altına düşerse iş akışından dosya
#: sessizce çıkarılmış demektir.
STEP_TEST_DOSYA_TABANI = 8


def _is_akisindan_step_dosyalari(komutlar):
    """`step-export` işinin GERÇEKTEN koşturduğu test dosyalarını türetir.

    İlacın emsali depoda yazılı: ``tests/test_i18n_common.py:67``
    (``PANEL_FILES = sorted(PANELS_DIR.glob('*.js'))``) — elle liste yerine
    kaynaktan türetme. Burada kaynak, işin kendi ``run`` komutlarıdır.

    YORUM SATIRLARI DÜŞÜRÜLÜR ve bu şart ölçümle bulundu: ``run: |`` bir YAML
    blok skaleridir, içindeki ``#`` satırları YAML yorumu DEĞİL kabuk
    yorumudur ve PyYAML onları aynen taşır. Düşürülmezse `step-export`
    adımının kendi açıklama satırındaki ``tests/test_ci_kapsam_kapisi.py``
    "koşulan dosya" sanılır: türetilen küme 8 yerine 9 çıkar ve alt sınır
    denetimi YANLIŞ gerekçeyle geçer (27 Ağustos 2026'da ölçüldü).
    """
    gercek_satirlar = [s for s in komutlar.splitlines()
                       if not s.lstrip().startswith("#")]
    return tuple(sorted(set(
        re.findall(r"tests/[\w./-]+\.py", "\n".join(gercek_satirlar)))))


def test_step_export_isi_gercekten_kosuyor():
    """H5-2: STEP/CAD bekçileri CI'da HER ZAMAN atlanıyordu.

    Ölçüm (3 Ağustos 2026, HEAD 9d3728e) — çekirdek beş dosya:
      * build123d KURULU ortam  : 143 passed, 2 xfailed, 0 atlandı
      * build123d YOK ortam (CI): 98 passed, **47 skipped**
    Yani 47 bekçi CI'da hiç koşmuyordu ve bu "yeşil" sayılıyordu.

    Sözleşme: ``tests.yml`` içinde build123d KURAN ve bu dosyaları koşturan
    ayrı bir iş bulunmalı. Sadece "iş var" yetmez — işin fail-closed olması
    gerekir, yoksa kütüphane kurulamadığında testler yine sessizce atlanır
    ve iş yeşil kalır.

    D1 (P13B1-08, 27 Ağustos 2026): (d) maddesi artık ELLE yazılmış beşliyi
    değil, iş akışından TÜRETİLEN kümeyi sınar. Türetilmiş kümeyi yine aynı
    komuta karşı sınamak totoloji olurdu; bu yüzden iki BAĞIMSIZ çapa
    kullanılır — ölçülmüş çekirdek (altküme şartı) ve ölçülmüş dosya sayısı
    tabanı. Bugün kırmızı üretmez: çekirdek beşli türetilen sekizin
    altkümesidir (ölçüldü).
    """
    metin = (ISAKISI_DIZINI / "tests.yml").read_text(encoding="utf-8")
    veri = _is_akisi_yukle("tests.yml")
    isler = veri["jobs"]
    assert "step-export" in isler, (
        "tests.yml'de 'step-export' işi yok — STEP bekçileri CI'da yine "
        f"atlanır (bulunan işler: {sorted(isler)})")

    adimlar = isler["step-export"]["steps"]
    komutlar = "\n".join(a.get("run", "") for a in adimlar)

    # (a) build123d gerçekten kurulmalı
    assert re.search(r"pip install\s+build123d", komutlar), (
        "step-export işi build123d kurmuyor")

    # (b) numpy pini geri alınmalı (build123d numpy 2.x'e yükseltir)
    assert re.search(r'pip install\s+"numpy[^"]*<2"', komutlar), (
        "build123d kurulumundan sonra numpy<2 pini geri alınmıyor")

    # (c) FAIL-CLOSED ortam teyidi: build123d yoksa/np pini bozuksa iş kırılır
    assert "BUILD123D_AVAILABLE" in komutlar, (
        "step_export.BUILD123D_AVAILABLE doğrulanmıyor — kütüphane "
        "kurulamazsa testler yine sessizce atlanır")

    # (d) koşan liste TÜRETİLİR, iki bağımsız çapaya karşı sınanır (D1)
    kosulan = _is_akisindan_step_dosyalari(komutlar)

    eksik = [d for d in STEP_TEST_CEKIRDEGI if d not in kosulan]
    assert not eksik, (
        "step-export işi ÖLÇÜLMÜŞ çekirdek dosyaları koşmuyor: "
        f"{eksik} — bunlar Faz 4'ün A1/A4/A8/A11 bulgularının bekçileridir "
        f"(işin koştuğu türetilmiş küme: {list(kosulan)})")

    assert len(kosulan) >= STEP_TEST_DOSYA_TABANI, (
        f"step-export işi yalnız {len(kosulan)} test dosyası koşuyor; "
        f"17 Ağustos 2026 ölçümü {STEP_TEST_DOSYA_TABANI} idi — iş akışından "
        f"dosya düşmüş olabilir (koşulan: {list(kosulan)}). Kasıtlıysa bu "
        "tabanı ölçümle birlikte güncelleyin.")


# ---------------------------------------------------------------------------
# ÖH FAZ F / F2 — atlama süzgeci: DİZGE denetimi yerine DAVRANIŞ denetimi
#
# Eski bekçi (3 Ağustos 2026 - 27 Ağustos 2026) süzgecin KAYNAK METNİNDE
# "pytest.skip" ve "pytest.xfail" dizgelerini arıyordu. Bu, kampanyanın
# adlandırdığı kusuru koruyan bekçi sınıfının ders kitabı örneğiydi: süzgeç
# modül DÜZEYİ atlamayı (junit XML'de ``type`` alanı OLMAYAN "collection
# skipped" satırı) hiç saymıyordu — yani bir test dosyasının tamamı sessizce
# yok olabiliyor, bekçi ise iki dizgeyi bulup yeşil kalıyordu (P13B1-06).
#
# Süzgeç artık iş akışından ÇIKARILIP sentetik bir junit raporuna karşı
# GERÇEKTEN KOŞTURULUYOR. Rapor uydurma değil: aşağıdaki üç atlama biçimi
# 27 Ağustos 2026'da pytest 8.4.2 ile üretilmiş gerçek çıktıdan alınmıştır
# (ölçüm: gövde içi ``pytest.skip`` + ``skipif`` işareti + modül düzeyi
# ``pytest.skip(allow_module_level=True)`` + modül başında ``importorskip``
# + ``xfail``). Ölçülen biçimler:
#   * gövde içi skip / skipif  -> <skipped type="pytest.skip" message="...">
#   * xfail                    -> <skipped type="pytest.xfail" message="...">
#   * modül düzeyi atlama      -> <skipped message="collection skipped"> ve
#                                 ``type`` alanı YOK; gerekçe düğüm METNİNDE
# ---------------------------------------------------------------------------

#: Sentetik junit raporu — F2 süzgecinin davranış tezgâhı.
#: 5 atlama (2 gövde/işaret + 1 ters kapı + 2 toplama düzeyi) + 1 xfail
#: (atlama SAYILMAZ) + 1 geçen test. ``tests`` sayısı, step-export işindeki
#: alt sınır denetimini (240) karıştırmamak için ölçümün üstünde tutulur.
SENTETIK_JUNIT_ATLAMA = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="0" failures="0" skipped="6" \
tests="300" time="1.0">
<testcase classname="tests.test_ornek" name="test_gecen" time="0.1" />
<testcase classname="tests.test_ornek" name="test_govde_skip" time="0.0">\
<skipped type="pytest.skip" message="govde ici pytest.skip">\
/x/tests/test_ornek.py:3: govde ici pytest.skip</skipped></testcase>
<testcase classname="tests.test_ornek" name="test_isaretli" time="0.0">\
<skipped type="pytest.skip" message="build123d kurulu degil (STEP uretimi \
atlanir)">/x/tests/test_ornek.py:9: atlandi</skipped></testcase>
<testcase classname="tests.test_ornek" name="test_ters_kapi" time="0.0">\
<skipped type="pytest.skip" message="build123d kurulu - .step sinaniyor">\
/x/tests/test_ornek.py:14: atlandi</skipped></testcase>
<testcase classname="tests.test_ornek" name="test_borc" time="0.0">\
<skipped type="pytest.xfail" message="borc imi" /></testcase>
<testcase classname="" name="tests.test_modul_skip" time="0.0">\
<skipped message="collection skipped">('/x/tests/test_modul_skip.py', 2, \
'Skipped: modul duzeyi atlama')</skipped></testcase>
<testcase classname="" name="tests.test_modul_ios" time="0.0">\
<skipped message="collection skipped">('/x/tests/test_modul_ios.py', 2, \
"Skipped: could not import 'build123d': No module named 'build123d'")\
</skipped></testcase>
</testsuite></testsuites>
"""


def _yml_python_govdesi(is_adi, adim_deseni):
    """`tests.yml` içindeki bir adımın heredoc Python gövdesini çıkarır."""
    veri = _is_akisi_yukle("tests.yml")
    adlar = []
    for adim in veri["jobs"][is_adi]["steps"]:
        ad = adim.get("name", "")
        adlar.append(ad)
        if re.search(adim_deseni, ad):
            eslesme = re.search(r"python\s+-\s+<<'PY'\n(.*?)\n\s*PY\s*$",
                                adim.get("run", ""), re.S)
            assert eslesme, (
                f"'{ad}' adımı `python - <<'PY' ... PY` kalıbında değil — "
                "süzgeç davranış olarak sınanamıyor")
            return eslesme.group(1)
    raise AssertionError(
        f"'{is_adi}' işinde /{adim_deseni}/ desenine uyan adım yok "
        f"(bulunan adımlar: {adlar})")


def _sentetik_rapora_karsi_kos(govde, rapor_adi, tmp_path, xml):
    """Süzgeç gövdesini sentetik junit raporuna karşı KOŞTURUR.

    ``xml=None`` verilirse rapor dosyası HİÇ YAZILMAZ (varsa silinir) —
    "rapor üretilmeden düşen koşum" hâlini sınamak için.

    Dönen: adımın çıkış kodu. ``sys.exit('mesaj')`` kabuğa 1 döndürür, yani
    "kırmızı" ölçütü ``cikis_kodu not in (0, None)``.
    """
    rapor = tmp_path / rapor_adi
    if xml is None:
        if rapor.exists():
            rapor.unlink()
    else:
        rapor.write_text(xml, encoding="utf-8")
    eski_dizin = os.getcwd()
    os.chdir(tmp_path)
    try:
        kod = compile(govde, f"<tests.yml::{rapor_adi}>", "exec")
        try:
            exec(kod, {"__name__": "__main__"})       # noqa: S102 — bilerek
        except SystemExit as cikis:
            return cikis.code
        return 0
    finally:
        os.chdir(eski_dizin)


def test_step_export_atlama_suzgeci_uc_atlama_bicimini_de_sayiyor(
        tmp_path, capsys):
    """F2 (P13B1-06): süzgeç DAVRANIŞ olarak sınanır, dizge olarak değil.

    Sentetik rapor 5 atlama taşır: 2 işaret/gövde skip'i, 1 ters kapı, 2
    MODÜL DÜZEYİ atlama; ayrıca 1 xfail (sayılmamalı) ve 1 geçen test.
    Eski süzgeç (``type == 'pytest.skip'``) modül düzeyindeki İKİSİNİ birden
    kaçırıyordu — bu bekçi tam olarak o farkı ölçer.
    """
    govde = _yml_python_govdesi("step-export", r"Atlama bütçesi")
    # ÖH D37 / YB-15: gövde "kanıt yok" önekini tek kaynaktan AST ile okur,
    # okuyamazsa düşer — tezgâha gerçek dosyalar KOPYALANIR (docs'suz ağaç).
    _tek_kaynagi_kur(tmp_path)
    _kanit_kaynagini_kur(tmp_path)
    kod = _sentetik_rapora_karsi_kos(govde, "step-report.xml", tmp_path,
                                     SENTETIK_JUNIT_ATLAMA)
    cikti = capsys.readouterr().out

    sayilar = re.search(
        r"atlanan=(\d+) \(ters_kapi=(\d+) gercek=(\d+) toplama_duzeyi=(\d+)\)",
        cikti)
    assert sayilar, (
        "süzgeç atlama sayımını basmıyor ya da toplama düzeyi atlamalarını "
        f"hiç raporlamıyor. Çıktı:\n{cikti}")
    atlanan, ters_kapi, gercek, toplama = (int(g) for g in sayilar.groups())

    assert atlanan == 5, (
        f"süzgeç {atlanan} atlama saydı, 5 olmalıydı — xfail sayılmış ya da "
        "modül düzeyi atlamalar (type alanı YOK) gözden kaçmış olabilir; "
        f"çıktı:\n{cikti}")
    assert toplama == 2, (
        f"modül düzeyi atlama sayısı {toplama}; sentetik raporda 2 var "
        "(biri allow_module_level, biri modül başındaki importorskip). "
        "Bunlar sayılmazsa bir test dosyasının tamamı sessizce yok olur "
        "(P13B1-06 / K8)")
    assert ters_kapi == 1, (
        f"ters kapı sayısı {ters_kapi}; sentetik raporda 1 var. DİKKAT: "
        "toplama düzeyi atlaması ters kapı SAYILAMAZ — ters kapı tek testi "
        "atlar, toplama atlaması dosyanın tamamını düşürür")
    assert gercek == 4, f"gerçek atlama sayısı {gercek}, 4 olmalıydı"
    assert kod not in (0, None), (
        "step-export bütçesi 4 gerçek atlamayı görüp kırmızıya dönmedi — "
        f"çıkış kodu {kod!r}, çıktı:\n{cikti}")


def test_step_export_isinde_atlama_butcesi_sifir():
    """H5-2: 'atlandı' başarı sayılamaz — bütçe SIFIR olmalı."""
    veri = _is_akisi_yukle("tests.yml")
    adimlar = veri["jobs"]["step-export"]["steps"]
    komutlar = "\n".join(a.get("run", "") for a in adimlar)

    assert "--junitxml=step-report.xml" in komutlar, (
        "atlama sayısı ölçülemiyor: junit raporu üretilmiyor")
    assert re.search(r"sys\.exit\(", komutlar), (
        "atlama bütçesi kırmızıya dönmüyor — yalnız bilgi basıyor")


# ---------------------------------------------------------------------------
# ÖH FAZ F / F1 — ana `pytest` işinin ÖLÇÜLMÜŞ atlama bütçesi (P13B1-07)
#
# 3-27 Ağustos 2026 arasında ana işte eşik YOKTU: 9497 testin ~9400'ünde
# "atlandı" mekanik olarak korunmasızdı. İş akışının kendi yorumu bunu dürüst
# bir gerekçeyle savunuyordu ("sayı ölçülmedi"). Sayı ölçüldü; bütçe kondu.
#
# Bu bekçiler bütçenin METNİNİ değil MEKANİZMASINI sınar: adımın Python
# gövdesi iş akışından çıkarılır ve sentetik junit raporlarına karşı
# koşturulur. Sınanan dört kaçış yolu (dördü de ölçülmüş kusur sınıfı):
#   1. bütçe aşımı                      -> kırmızı
#   2. modül düzeyi atlama (type YOK)   -> kırmızı  (P13B1-06 / K8)
#   3. toplamanın çökmesi               -> kırmızı  ("0 test, 0 atlama" yeşili)
#   4. depo-içi importorskip            -> kırmızı  (P13B1-05 / P14 §3.2-e)
# ---------------------------------------------------------------------------

ANA_IS_BUTCE_ADIMI = r"Atlama bütçesi"


def _sentetik_junit(atlama=0, toplama_duzeyi=0, xfail=0, gecen=1,
                    toplam=9500):
    """Ölçülen junit biçimlerinden sentetik rapor üretir.

    Biçimler 27 Ağustos 2026'da pytest 8.4.2 ile üretilen gerçek çıktıdan
    alınmıştır (bkz. ``SENTETIK_JUNIT_ATLAMA`` notu).
    """
    parcalar = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<testsuites><testsuite name="pytest" errors="0" failures="0" '
        f'tests="{toplam}" time="1.0">',
    ]
    for i in range(gecen):
        parcalar.append(
            f'<testcase classname="tests.test_x" name="test_g{i}" time="0.1" />')
    for i in range(atlama):
        parcalar.append(
            f'<testcase classname="tests.test_x" name="test_s{i}" time="0.0">'
            f'<skipped type="pytest.skip" message="atlama {i}">'
            f'/x/tests/test_x.py:{i}: atlama</skipped></testcase>')
    for i in range(xfail):
        parcalar.append(
            f'<testcase classname="tests.test_x" name="test_x{i}" time="0.0">'
            f'<skipped type="pytest.xfail" message="borc imi" /></testcase>')
    for i in range(toplama_duzeyi):
        parcalar.append(
            f'<testcase classname="" name="tests.test_m{i}" time="0.0">'
            f'<skipped message="collection skipped">'
            f"('/x/tests/test_m{i}.py', 2, 'Skipped: modul duzeyi atlama')"
            f'</skipped></testcase>')
    parcalar.append('</testsuite></testsuites>')
    return "\n".join(parcalar)


def _temiz_tests_dizini(tmp_path):
    """Bütçenin statik taraması için kusursuz bir `tests/` ağacı kurar."""
    dizin = tmp_path / "tests"
    dizin.mkdir(exist_ok=True)
    (dizin / "test_temiz.py").write_text(
        "import pytest\n"
        "yaml = pytest.importorskip('yaml')   # DIŞ paket — meşru\n"
        "def test_bir():\n    assert True\n",
        encoding="utf-8")
    return dizin


def _tek_kaynagi_kur(tmp_path):
    """Bütçenin TEK KAYNAĞINI (``tools/atlama_kapisi.py``) tmp ağacına koyar.

    ÖH D21 / defter OH-D17-19. Adımın gövdesi artık eşikleri kendi içinde
    YAZMIYOR, kaynak dosyadan AST ile okuyor. Gövde ``tmp_path`` içinde
    exec edildiği için kaynak orada da bulunmalı; KOPYALANIR, yeniden
    yazılmaz — böylece davranış bekçileri ürünün GERÇEK bütçesiyle koşar,
    kendi uydurdukları bir sayıyla değil.
    """
    hedef = tmp_path / "tools"
    hedef.mkdir(exist_ok=True)
    (hedef / "atlama_kapisi.py").write_text(
        (DEPO / "tools" / "atlama_kapisi.py").read_text(encoding="utf-8"),
        encoding="utf-8")
    return hedef / "atlama_kapisi.py"


def _kanit_kaynagini_kur(tmp_path):
    """"kanıt yok" önekinin TEK KAYNAĞINI (``tests/support/kanit.py``) kurar.

    ÖH D37 / YB-15. Adımın gövdesi öneki ve geliştirme ağacı işaretini bu
    dosyadan AST ile okur, okuyamazsa DÜŞER. KOPYALANIR, yeniden yazılmaz.
    ``tmp_path``te ``docs/scofield`` yoktur: tezgâh docs'suz ağaçtır.
    """
    hedef = tmp_path / "tests" / "support"
    hedef.mkdir(parents=True, exist_ok=True)
    shutil.copy(DEPO / "tests" / "support" / "kanit.py", hedef / "kanit.py")
    return hedef / "kanit.py"


def _ana_is_butcesini_kos(tmp_path, xml, tests_dizini=True, tek_kaynak=True,
                          kanit_kaynagi=True):
    if tests_dizini:
        _temiz_tests_dizini(tmp_path)
    if tek_kaynak:
        _tek_kaynagi_kur(tmp_path)
    if kanit_kaynagi:
        _kanit_kaynagini_kur(tmp_path)
    govde = _yml_python_govdesi("pytest", ANA_IS_BUTCE_ADIMI)
    return _sentetik_rapora_karsi_kos(
        govde, "pytest-report.xml", tmp_path, xml=xml)


def _butce_sayisi():
    """Adımın kullandığı bütçeyi TEK KAYNAKTAN okur.

    Eskiden sayı adımın gövdesinden regexle çekiliyordu; o biçim bütçenin
    ikinci tanım noktası olmasını ZORUNLU kılıyordu (OH-D17-19). Artık
    kaynak `tools/atlama_kapisi.ATLAMA_BUTCESI`dir ve bu yardımcı, adımın
    gövdesinde bir sayı KALMADIĞINI da ayrıca doğrular.
    """
    from tools.atlama_kapisi import ATLAMA_BUTCESI
    govde = _yml_python_govdesi("pytest", ANA_IS_BUTCE_ADIMI)
    kalinti = re.search(r"^\s*BUTCE\s*=\s*(\d+)\s*$", govde, re.M)
    assert not kalinti, (
        "ana `pytest` işinin gövdesinde bütçe SAYI olarak yeniden yazılmış "
        f"(BUTCE = {kalinti.group(1) if kalinti else ''}) — tek kaynak "
        "`tools/atlama_kapisi.ATLAMA_BUTCESI` kırılmış.")
    return int(ATLAMA_BUTCESI)


def test_ana_is_butcesi_tek_kaynagi_okuyamayinca_KIRMIZI(tmp_path, capsys):
    """OH-D17-19 / FAIL-CLOSED: kaynak yoksa eşik KAZANILMAMIŞTIR.

    Ters mutasyonun kendisi: `tools/atlama_kapisi.py` tmp ağacına
    konmadığında adım varsayılan bir sayıya düşmemeli, DÜŞMELİ.
    """
    kod = _ana_is_butcesini_kos(
        tmp_path, _sentetik_junit(atlama=0), tek_kaynak=False)
    cikti = capsys.readouterr().out
    assert kod not in (0, None), (
        "bütçenin tek kaynağı okunamadığı hâlde adım yeşil kaldı — "
        f"ölçülemeyen eşik geçmiş sayılamaz. Çıktı:\n{cikti}")


def test_ana_is_atlama_butcesi_asilinca_kirmizi(tmp_path, capsys):
    """F1: bütçe MEKANİZMASI çalışıyor mu — tam sınırda yeşil, +1'de kırmızı."""
    butce = _butce_sayisi()

    kod = _ana_is_butcesini_kos(tmp_path, _sentetik_junit(atlama=butce))
    cikti = capsys.readouterr().out
    assert kod in (0, None), (
        f"tam bütçe kadar ({butce}) atlamada iş kırmızıya döndü — bütçe "
        f"kullanılamaz derecede dar. Çıktı:\n{cikti}")

    kod = _ana_is_butcesini_kos(tmp_path, _sentetik_junit(atlama=butce + 1))
    cikti = capsys.readouterr().out
    assert kod not in (0, None), (
        f"{butce + 1} atlama bütçeyi ({butce}) aştı ama iş yeşil kaldı — "
        f"bütçe yalnız bilgi basıyor. Çıktı:\n{cikti}")

    # xfail atlama SAYILMAZ: borç imleri bütçeyi yemez.
    kod = _ana_is_butcesini_kos(
        tmp_path, _sentetik_junit(atlama=butce, xfail=200))
    cikti = capsys.readouterr().out
    assert kod in (0, None), (
        "200 xfail bütçeye sayıldı — borç imleri atlama değildir; junit "
        f"XML ikisini de <skipped> yazar, ayırt edici alan `type`. Çıktı:\n{cikti}")


def test_ana_is_butcesi_modul_dusmesini_ve_toplama_cokmesini_goruyor(
        tmp_path, capsys):
    """F1 × K8: sayıyla bütçelenemeyen iki kaçış yolu ayrıca kapalı."""
    # (a) TEK modül düzeyi atlama — bütçenin çok altında ama yine de kırmızı:
    #     tek satır görünür, dosyanın bütün testleri raporlanmadan kaybolur.
    kod = _ana_is_butcesini_kos(
        tmp_path, _sentetik_junit(atlama=1, toplama_duzeyi=1))
    cikti = capsys.readouterr().out
    assert kod not in (0, None), (
        "bir MODÜL toplama düzeyinde düştü (junit'te `type` alanı olmayan "
        "tek satır) ama bütçe yeşil kaldı — P13B1-06'nın tam olarak ölçtüğü "
        f"delik. Çıktı:\n{cikti}")

    # (b) toplama çöktü: 12 test toplandı, hiç atlama yok — "yeşil" görünür.
    kod = _ana_is_butcesini_kos(tmp_path, _sentetik_junit(toplam=12, gecen=12))
    cikti = capsys.readouterr().out
    assert kod not in (0, None), (
        "toplanan test sayısı 9497'den 12'ye düştü ama iş yeşil kaldı — "
        f"atlama bütçesi tek başına bu çöküşü görmez. Çıktı:\n{cikti}")

    # (c) rapor hiç yok: sayı ÖLÇÜLEMEZ, o hâlde geçer not verilemez.
    kod = _ana_is_butcesini_kos(tmp_path, None)
    cikti = capsys.readouterr().out
    assert kod not in (0, None), (
        "junit raporu yokken bütçe adımı sessizce 0 döndü — ölçülemeyen şey "
        f"geçmiş sayılamaz. Çıktı:\n{cikti}")


def test_ana_is_butcesi_depo_ici_importorskipi_sayiyor(tmp_path, capsys):
    """P14 §3.2-e: bütçe, depo-içi `importorskip` sitelerini de saymalı.

    Bu siteler KOŞTUĞUNDA görünmez — modül yerindeyken atlama üretmezler,
    yani dinamik atlama sayımı onları asla göremez. Görünür oldukları tek an
    modülün kırıldığı andır ve o anda bekçiyi kırmızı vermeden yok ederler.
    Bu yüzden bütçe adımı ayrıca STATİK tarama yapar.
    """
    dizin = _temiz_tests_dizini(tmp_path)
    (dizin / "test_depo_ici.py").write_text(
        "import pytest\n"
        "sabit = pytest.importorskip('hrma.engines.solid_rocket_engine')\n"
        "def test_bir():\n    assert sabit is not None\n",
        encoding="utf-8")

    kod = _ana_is_butcesini_kos(
        tmp_path, _sentetik_junit(atlama=0), tests_dizini=False)
    cikti = capsys.readouterr().out
    assert kod not in (0, None), (
        "tests/ altında depo-içi `pytest.importorskip` var ama bütçe yeşil "
        f"kaldı — P13B1-05 sessizce geri gelebilir. Çıktı:\n{cikti}")
    assert "hrma.engines.solid_rocket_engine" in cikti, (
        f"tarama kırmızı verdi ama siteyi adıyla söylemedi. Çıktı:\n{cikti}")


def test_depoda_depo_ici_importorskip_kalmadi():
    """P13B1-05 (kapanış bekçisi): `tests/` altında depo-içi ithal atlaması 0.

    Ölçüm (27 Ağustos 2026): 78 `pytest.importorskip` çağrısının 3'ü depo-içi
    modüle bakıyordu (`test_iki_faz_kayip.py:361`,
    `test_step_durustluk_kapisi.py:32`, `test_tank_step_units.py:37`);
    ikisi MODÜL DÜZEYİNDEydi, yani ithal kırıldığında o dosyaların tamamı
    (14 + 13 kalem) junit'te tek bir "collection skipped" satırına dönüşüp
    bütçeden kayboluyordu. Üçü de düz ithale çevrildi; bu bekçi geri
    gelmelerini engeller. Dış paketler (`build123d`, `ezdxf`, `yaml`…) bu
    yasağın DIŞINDADIR — onlar gerçekten isteğe bağlıdır.
    """
    import ast

    depo_kokleri = ("hrma", "app", "tools", "data")
    bulunan = []
    for yol in sorted((DEPO / "tests").rglob("test_*.py")):
        agac = ast.parse(yol.read_text(encoding="utf-8"))
        for dugum in ast.walk(agac):
            if (isinstance(dugum, ast.Call)
                    and isinstance(dugum.func, ast.Attribute)
                    and dugum.func.attr == "importorskip"
                    and dugum.args
                    and isinstance(dugum.args[0], ast.Constant)):
                hedef = str(dugum.args[0].value)
                if hedef.split(".")[0] in depo_kokleri:
                    bulunan.append(
                        f"{yol.relative_to(DEPO)}:{dugum.lineno} -> {hedef}")

    assert not bulunan, (
        "depo-içi `pytest.importorskip` geri geldi: " + "; ".join(bulunan) +
        " — modül DEPONUN KENDİSİ; 'isteğe bağlı bağımlılık' gerekçesi "
        "geçersiz. Düz ithale çevirin: kırılırsa bekçi DÜRÜSTÇE kırmızı "
        "vermeli, sessizce kaybolmamalı (P13B1-05).")


def test_yonetisim_bekcilerinin_bagimliligi_bildirilmis():
    """H5-4: PyYAML hiçbir requirements dosyasında yoktu.

    Ölçüm (3 Ağustos 2026): ``grep -in yaml requirements*.txt`` → 0 sonuç.
    Kurulu paketlerin hiçbiri PyYAML çekmiyordu (cantera ``ruamel.yaml``
    ister — farklı pakettir, ``import yaml`` sağlamaz). Sonuç: bu dosyadaki
    üç ``pytest.importorskip("yaml")`` CI'da her koşuda tetikleniyor ve
    4 yönetişim testi SESSİZCE atlanıyordu (E3 ve E5 bekçileri dahil).
    """
    metin = (DEPO / "requirements-dev.txt").read_text(encoding="utf-8")
    satirlar = [s.strip() for s in metin.splitlines()
                if s.strip() and not s.strip().startswith("#")]
    assert any(re.match(r"(?i)pyyaml\b", s) for s in satirlar), (
        "PyYAML requirements-dev.txt'de bildirilmemiş — yönetişim bekçileri "
        f"CI'da sessizce atlanır (bulunan: {satirlar})")

    # CI kurulumu doğrulamalı ki bağımlılık düşerse iş kırmızı olsun.
    ci = (ISAKISI_DIZINI / "tests.yml").read_text(encoding="utf-8")
    assert "import yaml" in ci, (
        "tests.yml PyYAML'in gerçekten kurulduğunu doğrulamıyor")


# ---------------------------------------------------------------------------
# E4 — VALIDATION_STATUS.md bayatlığı
# ---------------------------------------------------------------------------

ISARET_BAS = "<!-- AUTO-CORRELATION:BEGIN -->"
ISARET_SON = "<!-- AUTO-CORRELATION:END -->"


def _otomatik_blok():
    metin = DURUM_BELGESI.read_text(encoding="utf-8")
    assert ISARET_BAS in metin and ISARET_SON in metin
    return metin.split(ISARET_BAS, 1)[1].split(ISARET_SON, 1)[0].strip("\n")


def test_kaldirilan_thrust_satiri_belgede_yok():
    """E4: bayatlığın GÖRÜNEN yüzü — kaldırılmış hücre belgede duruyordu.

    ``tests/test_correlation_guards.py::test_f022_thrust_cell_absent``
    hücrenin KODDA üretilmemesini sınıyor; bu test aynı sözleşmenin
    BELGE tarafıdır. İkisi ayrı ayrı gerekli: koşucu hücreyi üretmeyi
    bıraktığı hâlde belge 9 gün boyunca satırı gösterdi.
    """
    blok = _otomatik_blok()
    for satir in blok.splitlines():
        hucreler = [h.strip() for h in satir.split("|")]
        assert hucreler[:4] != ["", "hybrid", "thrust", "main"], (
            "kaldırılan 'hybrid | thrust | main' satırı belgeye geri geldi: "
            f"{satir}")


def test_readme_bloga_always_current_demiyor():
    """E4(c): README bloğu "always-current" diye tanıtıyordu.

    Blok açık bir komutla üretiliyor; kendiliğinden tazelenmiyor. Belge
    9 gün bayat kalabildiğine göre bu sıfat gerçek değildi.
    """
    metin = (DEPO / "README.md").read_text(encoding="utf-8")
    assert "always-current" not in metin.lower(), (
        "README hâlâ korelasyon bloğuna 'always-current' diyor")


def test_belge_uretim_kaynagini_beyan_ediyor():
    """E4(a): blok hangi commit'ten ve hangi koşucu sürümüyle üretildi?"""
    metin = DURUM_BELGESI.read_text(encoding="utf-8")

    eslesme = re.search(r"\b([0-9a-f]{40})\b", metin)
    assert eslesme, "belge üretim commit'ini (tam SHA) beyan etmiyor"
    belge_sha = eslesme.group(1)

    blok = _otomatik_blok()
    assert re.search(r"- Generated: \d{4}-\d{2}-\d{2} \(runner v\d+, adapter v\d+\)",
                     blok), "blok üretim tarihi/koşucu sürümü taşımıyor"

    # SHA uydurma olmamalı: depoda gerçekten bir commit olsun.
    sig = subprocess.run(["git", "-C", str(DEPO), "rev-parse",
                          "--is-shallow-repository"],
                         capture_output=True, text=True, timeout=60)
    if sig.returncode != 0:
        pytest.skip("git yok — SHA doğrulanamıyor")
    if sig.stdout.strip() == "true":
        pytest.skip("sığ klon — geçmiş commit nesnesi yerelde olmayabilir")

    tur = subprocess.run(["git", "-C", str(DEPO), "cat-file", "-t", belge_sha],
                         capture_output=True, text=True, timeout=60)
    assert tur.returncode == 0 and tur.stdout.strip() == "commit", (
        f"belgedeki {belge_sha[:8]} bu depoda bir commit değil")


def test_otomatik_blok_bugunku_kodun_urettigiyle_ayni():
    """E4(b): belge BAYATSA bu test KIRILIR — CI bayatlığı yakalar.

    Korelasyon yeniden koşturulur ve blok yeniden üretilip belgedekiyle
    karşılaştırılır. Denetimde ölçülen bayatlık tam olarak buydu: belge
    2026-07-24 koşusunu taşıyordu, kod ise üç satırı farklı üretiyordu
    (kaldırılmış thrust hücresi + değişmiş hibrit regresyon oranı).

    Tarih satırı kasten belgenin KENDİ beyan ettiği tarihle üretilir:
    aksi hâlde test ertesi gün, içerik hiç değişmeden kırmızıya döner ve
    kimsenin okumadığı bir alarma dönüşür. Ölçülen şey tazelik değil,
    SAYILARIN bugünkü kodla uyuşması.

    Süre: korelasyon koşusu ~2 dk (95 kayıt skorlanıyor).
    """
    import contextlib

    # DEPO-İÇİ ``pytest.importorskip`` KALDIRILDI — P14S1-03 / P13B1-05,
    # ÖH Faz B-1 adım 10 (2026-08-26).
    #
    # Eski gövde ``correlation_runner = pytest.importorskip(
    # "hrma.validation.correlation_runner")`` idi. Bu modül DEPONUN KENDİSİdir;
    # "isteğe bağlı bağımlılık" gerekçesi burada geçerli değil (dosya başındaki
    # PyYAML notu yalnız DIŞ paketler için yazılmıştır — o not duruyor).
    #
    # ÖLÇÜLDÜ (bellekte-yama ile iki modülün import'u kırılarak, 2026-08-26):
    #   eski gövde -> "1 skipped"  — korelasyon koşucusu kırıldığında bekçi
    #                                KIRMIZI VERMEDEN yok oluyordu;
    #   bu gövde   -> "1 failed"   — ImportError gövdede patlar, dürüstçe kırmızı.
    # Ağırlığı ölçülü: P14'ün mutasyon taramasında HTPB ``a`` katsayısının
    # %20 bozulmasını yakalayan İKİ bekçiden biri tam olarak bu testtir
    # (P14M2-14). Yani kampanyanın en güçlü sabit bekçilerinden biri, bir
    # import hatasıyla sessizce kaybolabiliyordu.
    from hrma.validation import correlation_runner, status_report

    belgedeki = _otomatik_blok()
    tarih_eslesme = re.search(r"- Generated: (\d{4}-\d{2}-\d{2})", belgedeki)
    assert tarih_eslesme, "blokta üretim tarihi yok"

    with open(os.devnull, "w", encoding="utf-8") as bosluk, \
            contextlib.redirect_stdout(bosluk):
        sonuc = correlation_runner.run_correlation()

    uretilen = status_report.generate_status_section(
        sonuc, generated_on=tarih_eslesme.group(1))

    if uretilen.strip() != belgedeki.strip():
        import difflib
        fark = "\n".join(difflib.unified_diff(
            belgedeki.strip().splitlines(),
            uretilen.strip().splitlines(),
            fromfile="docs/VALIDATION_STATUS.md (belge)",
            tofile="bugunku kodun urettigi", lineterm=""))
        pytest.fail(
            "VALIDATION_STATUS.md korelasyon bloğu BAYAT — belgedeki sayılar "
            "bugünkü kodun ürettiği sayılar değil. Elle düzeltme: "
            "`python3 -m hrma.validation.status_report`\n\n" + fark)


# ---------------------------------------------------------------------------
# E5 — yönetişim dosyaları
# ---------------------------------------------------------------------------

def test_yonetisim_dosyalarinin_hepsi_var():
    """E5: yedisi de yoktu (denetimde ``find`` ile doğrulandı)."""
    beklenen = [
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODEOWNERS",
        ".pre-commit-config.yaml",
        "CITATION.cff",
        ".github/workflows/release.yml",
    ]
    eksik = [ad for ad in beklenen if not (DEPO / ad).exists()]
    assert not eksik, f"yönetişim dosyaları eksik: {eksik}"

    # Sus payı olmasın: her biri gerçek içerik taşımalı.
    for ad in beklenen:
        boyut = (DEPO / ad).stat().st_size
        assert boyut > 500, f"{ad} yalnız {boyut} bayt — içeriksiz"


def test_security_bildirim_kanali_ve_dogru_beyanlar():
    metin = (DEPO / "SECURITY.md").read_text(encoding="utf-8")

    assert "btezgocen97@gmail.com" in metin, "bildirim kanalı yok"
    assert "Supported versions" in metin
    assert re.search(r"\b90 days\b", metin), "açıklama süresi belirtilmemiş"

    # Kabul edilen zayıflıklar açıkça yazılmalı — imza altyapısı bu fazın
    # kapsamı dışında, ama BU DURUM gizlenmemeli.
    dusuk = metin.lower()
    assert "ad-hoc" in dusuk and "notariz" in dusuk, (
        "imzalama sınırı beyan edilmemiş")


def test_contributing_gercek_yollari_gosteriyor():
    """CONTRIBUTING uydurma komut/yol içermemeli.

    Depoda olmayan bir dosyaya yönlendiren katkı kılavuzu, katkıcının ilk
    yarım saatini çalar ve projeye güveni bozar. Tek istisna, kılavuzun
    "bunları commit etme" diye andığı gitignore'lu yapı çıktısı dizinleri.
    """
    metin = (DEPO / "CONTRIBUTING.md").read_text(encoding="utf-8")

    desen = re.compile(
        r"`([A-Za-z0-9_./*-]+(?:\.(?:py|md|txt|ya?ml|json|sh|cff)|/))`")
    adaylar = set(desen.findall(metin)) - YAPI_CIKTISI_DIZINLERI

    eksik = []
    for aday in sorted(adaylar):
        if "*" in aday:
            if not glob.glob(str(DEPO / aday)):
                eksik.append(aday)
        elif not (DEPO / aday).exists():
            eksik.append(aday)
    assert not eksik, f"CONTRIBUTING var olmayan yolları gösteriyor: {eksik}"

    # Yazdığı test komutu gerçekten bu deponun komutu olmalı.
    assert "pytest tests/" in metin
    assert "MPLBACKEND=Agg" in metin and "PYTHONPATH=." in metin
    # Yayın bölümü iki gerçek kazayı ve mekanik kapıyı anlatmalı.
    assert "release_gate.sh" in metin and "KAPIYI_ATLA" in metin


def test_codeowners_kritik_yollari_kapsiyor():
    metin = (DEPO / "CODEOWNERS").read_text(encoding="utf-8")

    kayitlar = {}
    for satir in metin.splitlines():
        satir = satir.split("#", 1)[0].strip()
        if not satir:
            continue
        parcalar = satir.split()
        if len(parcalar) >= 2:
            kayitlar[parcalar[0]] = parcalar[1:]

    for yol in ("/hrma/engines/", "/hrma/analysis/", "/packaging/"):
        assert yol in kayitlar, f"kritik yolun sahibi yok: {yol}"
        assert all(sahip.startswith("@") for sahip in kayitlar[yol])

    # Var olmayan yola sahiplik atamak, korumayı olduğundan geniş gösterir.
    eksik = [yol for yol in kayitlar
             if yol not in ("*",) and not (DEPO / yol.lstrip("/")).exists()]
    assert not eksik, f"CODEOWNERS var olmayan yolları gösteriyor: {eksik}"


def test_pre_commit_yerel_kancasi_var_olan_betigi_cagirir():
    """Ayrıştırıcısız çekirdek denetim: hook olmayan bir betiği çağırmamalı."""
    metin = (DEPO / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    girdiler = re.findall(r"^\s*entry:\s*(.+?)\s*$", metin, re.M)
    assert girdiler, "projeye özgü hiç kontrol yok"
    for girdi in girdiler:
        betik = girdi.split()[-1]
        assert (DEPO / betik).exists(), (
            f"pre-commit var olmayan betiği çağırıyor: {betik}")


def test_pre_commit_yapilandirmasi_calisir():
    yaml = pytest.importorskip(
        "yaml", reason="PyYAML kurulu değil — derin YAML denetimi atlandı")
    veri = yaml.safe_load(
        (DEPO / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    depolar = veri["repos"]
    assert depolar, "hiç hook yok"

    yerel_girdiler = []
    for kayit in depolar:
        kancalar = kayit.get("hooks") or []
        assert kancalar, f"{kayit.get('repo')}: hook listesi boş"
        if kayit["repo"] == "local":
            yerel_girdiler += [kanca["entry"] for kanca in kancalar]
        else:
            # Sürümsüz uzak hook, denetimi üçüncü tarafın eline bırakır.
            assert kayit.get("rev"), f"{kayit['repo']}: rev pinlenmemiş"

    # Yerel hook gerçekten var olan bir betiği çağırmalı.
    assert yerel_girdiler, "projeye özgü hiç kontrol yok"
    for girdi in yerel_girdiler:
        betik = girdi.split()[-1]
        assert (DEPO / betik).exists(), f"pre-commit olmayan betiği çağırıyor: {betik}"

    # ------------------------------------------------------------------
    # Büyük dosya tavanı.
    #
    # ÖH D15 birleştirme (1 Eyl 2026) — BEKÇİ ÇEVRİLDİ. Buradaki iddia
    # "tavan, izlenen en büyük dosyanın ÜSTÜNDE olmalı; altında olursa hook
    # temiz ağaçta kırmızı yanar" idi. Birleşmeden sonra gerçekten kırmızı
    # yandı (fea-viz kulvarının iki ham kanıt dökümü 24.296 / 23.933 KB),
    # AMA İDDİANIN KENDİSİ ÖLÇÜMLE YANLIŞ ÇIKTI:
    #
    #     $ pre-commit run check-added-large-files --all-files
    #     check for added large files..............................Passed
    #
    # ``check-added-large-files`` — adının söylediği gibi — YALNIZ o
    # commit'te EKLENEN dosyalara bakar; zaten izlenen bir dosya
    # ``--enforce-all`` verilmedikçe kapsam dışıdır. Yani tavanı 24 MB'ın
    # üstüne çıkarmak "temiz ağaç kırmızısını" ÖNLEMEZ (öyle bir kırmızı
    # yok); yalnızca bundan SONRA eklenecek dev dosyalara kapıyı açardı —
    # kusuru gizleyen bir gevşetme olurdu. Tavan bu yüzden 10240'ta KALIR.
    #
    # Ölçülen davranışa göre iki ayrı iddia kilitlenir:
    #   1. ``--enforce-all`` VARSA eski koşul geçerlidir (hook o zaman
    #      gerçekten bütün ağaca bakar): tavan en büyüğün üstünde olmalı.
    #   2. Yoksa yapılandırma ağacın gerçeğini YANLIŞ ANLATMAMALIDIR. Yanlış
    #      beyan sonraki bakımcıya ağacın temiz olduğunu söyler ve
    #      ``--enforce-all`` eklendiği gün kapı sessizce patlar.
    tavan_kb = None
    enforce_all = False
    for kayit in depolar:
        for kanca in kayit.get("hooks") or []:
            if kanca.get("id") == "check-added-large-files":
                for arguman in kanca.get("args", []):
                    if arguman.startswith("--maxkb="):
                        tavan_kb = int(arguman.split("=", 1)[1])
                    if arguman == "--enforce-all":
                        enforce_all = True
    if tavan_kb is not None:
        listeleme = subprocess.run(["git", "-C", str(DEPO), "ls-files"],
                                   capture_output=True, text=True, timeout=120)
        assert listeleme.returncode == 0, "git ls-files koşmadı — ölçüm yok"
        en_buyuk, en_buyuk_yol = 0, None
        for yol in listeleme.stdout.splitlines():
            tam = DEPO / yol
            if tam.is_file() and tam.stat().st_size > en_buyuk:
                en_buyuk, en_buyuk_yol = tam.stat().st_size, yol
        if enforce_all:
            assert en_buyuk / 1024 < tavan_kb, (
                f"--enforce-all verilmiş: hook BÜTÜN ağaca bakar. İzlenen en "
                f"büyük dosya {en_buyuk / 1024:.0f} KB ({en_buyuk_yol}), tavan "
                f"{tavan_kb} KB — hook temiz ağaçta kırmızı yanar")
        else:
            metin = (DEPO / ".pre-commit-config.yaml").read_text(
                encoding="utf-8")
            asiyor = en_buyuk / 1024 >= tavan_kb
            beyan = re.search(
                r"[Cc]eiling is above the largest tracked file", metin)
            assert not (asiyor and beyan), (
                f".pre-commit-config.yaml 'ceiling is above the largest "
                f"tracked file' diye bir OLGU beyan ediyor ama beyan yanlış: "
                f"{en_buyuk_yol} {en_buyuk / 1024:.0f} KB >= tavan "
                f"{tavan_kb} KB. Beyan düzeltilmeli (ya da dosya "
                f"küçültülmeli). TAVANI BÜYÜTMEK ÇÖZÜM DEĞİL: temiz ağaç "
                f"kırmızısı diye bir şey yok — hook --enforce-all olmadan "
                f"izlenen dosyaya hiç bakmıyor — büyütmek yalnız gelecekteki "
                f"dev eklemelere kapıyı açar.")


def test_citation_cff_zorunlu_alanlari_var():
    """Ayrıştırıcısız çekirdek denetim: CFF'in zorunlu anahtarları."""
    metin = (DEPO / "CITATION.cff").read_text(encoding="utf-8")
    for anahtar in ("cff-version:", "message:", "title:", "authors:",
                    "version:", "date-released:"):
        assert re.search(rf"^{re.escape(anahtar)}", metin, re.M), (
            f"CITATION.cff '{anahtar}' alanı eksik")
    assert "Tezgöçen" in metin and "Berke" in metin


def test_citation_cff_gecerli():
    yaml = pytest.importorskip(
        "yaml", reason="PyYAML kurulu değil — derin YAML denetimi atlandı")
    veri = yaml.safe_load((DEPO / "CITATION.cff").read_text(encoding="utf-8"))

    for anahtar in ("cff-version", "message", "title", "authors"):
        assert veri.get(anahtar), f"CITATION.cff '{anahtar}' alanı eksik"
    assert str(veri["cff-version"]).startswith("1.2")

    yazarlar = veri["authors"]
    assert isinstance(yazarlar, list) and yazarlar
    assert yazarlar[0]["family-names"] == "Tezgöçen"
    assert yazarlar[0]["given-names"] == "Berke"

    # Atıf, okurun GERÇEKTEN indirebileceği bir sürümü göstermeli:
    # yayınlanmış son sürüm (changelog'da var) ve paket sürümünden ileri
    # olamaz. Bilinçli olarak paket sürümüne EŞİT olması beklenmez —
    # 2.6.26 henüz yayınlanmamışken CITATION 2.6.25'i gösterir.
    import json
    surum = str(veri["version"])
    changelog = json.loads(
        (DEPO / "hrma" / "data" / "changelog.json").read_text(encoding="utf-8"))
    bilinen = [girdi["version"] for girdi in changelog["versions"]]
    assert surum in bilinen, (
        f"CITATION.cff sürümü {surum} changelog'da yok — yayınlanmamış "
        f"ya da uydurma bir sürüme atıf veriyor")

    def _ayristir(metin):
        return tuple(int(parca) for parca in metin.split("."))

    paket = re.search(r'^__version__ = "(.*)"',
                      (DEPO / "hrma" / "__init__.py").read_text(encoding="utf-8"),
                      re.M).group(1)
    assert _ayristir(surum) <= _ayristir(paket), (
        f"CITATION.cff sürümü {surum}, paket {paket}'ten ileri")

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(veri["date-released"]))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
