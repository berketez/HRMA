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
    """Kapı betiğini ``baslik "N/8 ..."`` sınırlarından bölümlere ayırır.

    2026-08-04: kapıya 8. adım (paket içerik manifesti + boyut sapması)
    eklendi; ayrıştırıcı /7'den /8'e güncellendi.
    """
    metin = KAPI_BETIGI.read_text(encoding="utf-8")
    parcalar = re.split(r'^baslik "(\d)/8\s+([^"]*)"', metin, flags=re.M)
    bolumler = {}
    for indeks in range(1, len(parcalar), 3):
        bolumler[int(parcalar[indeks])] = parcalar[indeks + 2]
    return bolumler


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


def test_kapi_sekiz_adimin_hepsini_iceriyor():
    bolumler = _kapi_bolumleri()
    assert sorted(bolumler) == list(range(1, 9)), sorted(bolumler)


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
                f"{numara}/8 adımı '{bayrak}' atlama bayrağını görüyor — "
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
    """İş akışını ayrıştırır. PyYAML yoksa testi ATLAR (bkz. üstteki not)."""
    yaml = pytest.importorskip(
        "yaml", reason="PyYAML kurulu değil — derin YAML denetimi atlandı")
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

#: `step-export` işinin gerçekten koşturması gereken STEP/CAD test dosyaları.
#: Bunlar Faz 4'ün A1 (STL/DXF 1000× birim hatası), A4 (NaN geometriden katı
#: cisim), A8 (katı cidarı) ve A11 (tank geometrisi) bulgularının bekçileridir.
STEP_TEST_DOSYALARI = (
    "tests/test_step_import.py",
    "tests/test_tank_step_units.py",
    "tests/test_faz4_export_geometri.py",
    "tests/test_faz4_app_export.py",
    "tests/test_export_generators.py",
)


def test_step_export_isi_gercekten_kosuyor():
    """H5-2: STEP/CAD bekçileri CI'da HER ZAMAN atlanıyordu.

    Ölçüm (3 Ağustos 2026, HEAD 9d3728e) — yukarıdaki beş dosya:
      * build123d KURULU ortam  : 143 passed, 2 xfailed, 0 atlandı
      * build123d YOK ortam (CI): 98 passed, **47 skipped**
    Yani 47 bekçi CI'da hiç koşmuyordu ve bu "yeşil" sayılıyordu.

    Sözleşme: ``tests.yml`` içinde build123d KURAN ve bu beş dosyayı
    koşturan ayrı bir iş bulunmalı. Sadece "iş var" yetmez — işin
    fail-closed olması gerekir, yoksa kütüphane kurulamadığında testler
    yine sessizce atlanır ve iş yeşil kalır.
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

    # (d) beş dosyanın beşi de koşmalı
    for dosya in STEP_TEST_DOSYALARI:
        assert dosya in komutlar, f"step-export işi {dosya} koşmuyor"


def test_step_export_isinde_atlama_butcesi_sifir():
    """H5-2: 'atlandı' başarı sayılamaz — bütçe SIFIR olmalı.

    Bu işte atlama bütçesi 0'dır: gerçek bir ``pytest.skip`` çıkarsa iş
    kırmızıya döner. ``xfail`` atlama sayılmaz (junit XML xfail'i de
    ``<skipped>`` olarak yazar; ayırt edici alan ``type``'tır).
    """
    veri = _is_akisi_yukle("tests.yml")
    adimlar = veri["jobs"]["step-export"]["steps"]
    komutlar = "\n".join(a.get("run", "") for a in adimlar)

    assert "--junitxml=step-report.xml" in komutlar, (
        "atlama sayısı ölçülemiyor: junit raporu üretilmiyor")
    assert "pytest.skip" in komutlar and "pytest.xfail" in komutlar, (
        "atlama denetimi gerçek skip ile xfail'i ayırt etmiyor")
    assert re.search(r"sys\.exit\(", komutlar), (
        "atlama bütçesi kırmızıya dönmüyor — yalnız bilgi basıyor")


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

    correlation_runner = pytest.importorskip(
        "hrma.validation.correlation_runner")
    status_report = pytest.importorskip("hrma.validation.status_report")

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

    # Büyük dosya tavanı, izlenen en büyük dosyanın ÜSTÜNDE olmalı; altında
    # olursa hook temiz bir ağaçta bile kırmızı yanar.
    tavan_kb = None
    for kayit in depolar:
        for kanca in kayit.get("hooks") or []:
            if kanca.get("id") == "check-added-large-files":
                for arguman in kanca.get("args", []):
                    if arguman.startswith("--maxkb="):
                        tavan_kb = int(arguman.split("=", 1)[1])
    if tavan_kb is not None:
        listeleme = subprocess.run(["git", "-C", str(DEPO), "ls-files"],
                                   capture_output=True, text=True, timeout=120)
        if listeleme.returncode == 0:
            en_buyuk = 0
            for yol in listeleme.stdout.splitlines():
                tam = DEPO / yol
                if tam.is_file():
                    en_buyuk = max(en_buyuk, tam.stat().st_size)
            assert en_buyuk / 1024 < tavan_kb, (
                f"izlenen en büyük dosya {en_buyuk / 1024:.0f} KB, "
                f"tavan {tavan_kb} KB — hook temiz ağaçta kırmızı yanar")


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
