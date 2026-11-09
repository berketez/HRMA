"""3.0.6 CI-SÜREÇ — yayın betiklerindeki iki süreç hatasının bekçileri.

YAYIN-1 (``packaging/publish_release.sh``)
------------------------------------------
v3.0.5 (28 Eki 2026) ölçülen sıra (``gh run list --commit 0a138ff6a``,
kanıt ``docs/scofield/raw/OH/V306/ci-surec/gh_run_list_v305_0a138ff6a.json``):

    18:39-19:34 UTC  aday dalı (workflow_dispatch) 'tests' YEŞİL
    19:36-20:33 UTC  main push aynı SHA için 'tests'i YENİDEN koştu
    20:54 UTC        sürüm açıldı

``gh release create`` ``--target`` almadığı için etiket varsayılan dalın
(main) o anki ucuna açılırdı; bu yüzden main yayından ÖNCE push edilmek
zorundaydı. Bekçi: etiket kapının doğruladığı commit'e (``HEAD``) açılır;
uzakta başka commit'i gösteren etiket varsa (gh o durumda ``--target``'ı
sessizce yok sayar) yayın yapılmaz; HEAD kapıdan sonra değişirse yayın yok.

YAYIN-2 (``packaging/release_gate.sh`` 4/10)
--------------------------------------------
Aynı SHA'nın yeşil 'tests' koşusu varken süren 'tests' kopyası artık
beklenmez (BİLGİ satırı); iptal edilmiş/başarısız koşu ve 'tests' dışındaki
süren iş akışı yine KALDI. Karar işlevi (``ci_kosulari_degerlendir``) kapı
betiğinden ÇIKARILIP ``gh run list`` çıktısını taklit eden fikstürlerle
koşturulur — kopyalanmaz, yani betik değişince test de değişen kodu ölçer.

Hiçbir test ağa çıkmaz ve hiçbir şey yayınlamaz: ``gh`` yerine çağrıları
diske yazan bir vekil konur.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

DEPO = Path(__file__).resolve().parents[1]
YAYIN_BETIGI = DEPO / "packaging" / "publish_release.sh"
KAPI_BETIGI = DEPO / "packaging" / "release_gate.sh"

#: Gerçek bir sürümle karışmasın diye imkânsız sürüm numarası.
SAHTE_SURUM = "9.9.9"

#: Kapının ölçtüğü SHA (fikstürlerde) — 40 onaltılık, gerçek bir commit değil.
SHA_A = "a" * 40
SHA_B = "b" * 40


# ---------------------------------------------------------------------------
# Ortak: sahte git deposu + gh vekili
# ---------------------------------------------------------------------------

def _git(kok, *argumanlar, **kw):
    komut = ["git", "-C", str(kok), "-c", "core.hooksPath=/dev/null",
             "-c", "commit.gpgsign=false", "-c", "user.name=sahte",
             "-c", "user.email=sahte@ornek.invalid", *argumanlar]
    return subprocess.run(komut, check=True, capture_output=True, text=True,
                          timeout=60, **kw).stdout.strip()


def _yayin_tezgahi(tmp_path, kapi_govdesi="exit 0\n", git_deposu=True):
    """publish_release.sh'i gerçekten koşturmak için sahte depo kurar.

    Betik ``SRC``yi kendi konumundan türettiği için ``<kök>/packaging/``
    altına kopyalanan betik tümüyle bu ağaca hapsolur.

    Döndürür: (kök, kayıt dizini, bin dizini, HEAD SHA ya da None)
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
    (kok / "packaging" / f"release_notes_v{SAHTE_SURUM}.md").write_text(
        "<!--HRMA-LANG:en-->\nEnglish notes\n"
        "<!--HRMA-LANG:tr-->\nTürkçe notlar\n", encoding="utf-8")
    (kok / "README.md").write_text(
        f"HRMA-Setup-{SAHTE_SURUM}-macOS.dmg\n", encoding="utf-8")
    kapi = kok / "packaging" / "release_gate.sh"
    kapi.write_text("#!/bin/bash\n" + kapi_govdesi, encoding="utf-8")
    kapi.chmod(0o755)

    # gh vekili: her çağrıyı ayrı dosyaya yazar (gh_<n>.txt, satır başına
    # bir argüman). `api` çağrılarına kayıt dizinindeki cevap dosyalarıyla
    # yanıt verir — bunlar gerçek gh'nin --jq SONRASI çıktısının biçimidir
    # (tür<TAB>sha). Cevap dosyası yoksa boş çıktı = etiket yok.
    bin_dizin = tmp_path / "bin"
    bin_dizin.mkdir()
    gh = bin_dizin / "gh"
    gh.write_text(
        "#!/bin/bash\n"
        f'K="{kayit}"\n'
        'n=$(ls "$K"/gh_*.txt 2>/dev/null | wc -l | tr -d " ")\n'
        'printf "%s\\n" "$@" > "$K/gh_$n.txt"\n'
        'if [ "$1" = "api" ]; then\n'
        '    [ -f "$K/api_cikis.txt" ] && exit "$(cat "$K/api_cikis.txt")"\n'
        '    case "$2" in\n'
        '        */git/matching-refs/*) [ -f "$K/cevap_ref.txt" ] && cat "$K/cevap_ref.txt" ;;\n'
        '        */git/tags/*) [ -f "$K/cevap_tag.txt" ] && cat "$K/cevap_tag.txt" ;;\n'
        '    esac\n'
        'fi\n'
        "exit 0\n", encoding="utf-8")
    gh.chmod(0o755)

    head = None
    if git_deposu:
        _git(kok, "init", "-q")
        _git(kok, "add", "-A")
        _git(kok, "commit", "-q", "-m", "sahte depo")
        head = _git(kok, "rev-parse", "HEAD")
    return kok, kayit, bin_dizin, head


def _kostur(kok, bin_dizin, betik=None):
    ortam = dict(os.environ)
    ortam["PATH"] = f"{bin_dizin}{os.pathsep}{ortam['PATH']}"
    for anahtar in ("TASLAK", "KAPIYI_ATLA", "KAPIYI_ATLA_GEREKCE"):
        ortam.pop(anahtar, None)
    # Sahte depo bir üst depoya (ör. tmp altında) bağlanmasın.
    ortam["GIT_CEILING_DIRECTORIES"] = str(kok.parent)
    return subprocess.run(
        ["bash", str(betik or (kok / "packaging" / "publish_release.sh"))],
        capture_output=True, text=True, timeout=180, env=ortam, cwd=str(kok))


def _gh_cagrilari(kayit):
    """Sırasıyla bütün gh çağrılarının argüman listeleri."""
    dosyalar = sorted(kayit.glob("gh_*.txt"),
                      key=lambda p: int(p.stem.split("_")[1]))
    return [p.read_text(encoding="utf-8").splitlines() for p in dosyalar]


def _yayin_cagrisi(kayit):
    """``gh release create`` çağrısının argümanları; yoksa None."""
    for cagri in _gh_cagrilari(kayit):
        if cagri[:2] == ["release", "create"]:
            return cagri
    return None


def _hedef(argumanlar):
    assert "--target" in argumanlar, (
        "gh release create --target'sız çağrıldı — etiket varsayılan dalın "
        "ucuna açılır (v3.0.5 YAYIN-1): %s" % argumanlar)
    return argumanlar[argumanlar.index("--target") + 1]


# ---------------------------------------------------------------------------
# YAYIN-1 — publish_release.sh
# ---------------------------------------------------------------------------

def test_yayin1_etiket_yayinlanan_shaya_acilir(tmp_path):
    """Etiket varsayılan dalın ucuna değil, kapının doğruladığı HEAD'e açılır."""
    kok, kayit, bin_dizin, head = _yayin_tezgahi(tmp_path)
    sonuc = _kostur(kok, bin_dizin)

    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    argumanlar = _yayin_cagrisi(kayit)
    assert argumanlar is not None, "kapı yeşilken yayın yapılmadı"
    assert _hedef(argumanlar) == head
    assert re.fullmatch(r"[0-9a-f]{40}", head)
    # Uzaktaki etiket yayından ÖNCE ölçüldü (gh --target'ı mevcut etikette
    # yok sayar; ölçüm olmadan bu durum görünmez).
    cagrilar = _gh_cagrilari(kayit)
    sira = [c[:2] for c in cagrilar]
    assert ["release", "create"] in sira
    olcum = [i for i, c in enumerate(cagrilar)
             if c[:1] == ["api"] and "/git/matching-refs/tags/v%s" % SAHTE_SURUM in c[1]]
    assert olcum and olcum[0] < sira.index(["release", "create"]), sira


def test_yayin1_head_okunamazsa_yayin_yok(tmp_path):
    """git deposu olmayan ağaçta SHA okunamaz -> yayın YOK (boş --target yok)."""
    kok, kayit, bin_dizin, _ = _yayin_tezgahi(tmp_path, git_deposu=False)
    sonuc = _kostur(kok, bin_dizin)

    assert sonuc.returncode != 0, "SHA okunamadan yayın yapıldı"
    assert _yayin_cagrisi(kayit) is None
    assert "HEAD" in sonuc.stdout


def test_yayin1_uzakta_baska_committe_etiket_varsa_yayin_yok(tmp_path):
    """Etiket uzakta başka commit'i gösteriyorsa gh --target'ı yok sayardı."""
    kok, kayit, bin_dizin, _ = _yayin_tezgahi(tmp_path)
    (kayit / "cevap_ref.txt").write_text(f"commit\t{SHA_B}\n", encoding="utf-8")
    sonuc = _kostur(kok, bin_dizin)

    assert sonuc.returncode != 0, sonuc.stdout
    assert _yayin_cagrisi(kayit) is None, "yanlış commit'teki etikete yayın açıldı"
    assert "ZATEN VAR" in sonuc.stdout


def test_yayin1_uzakta_ayni_committe_etiket_varsa_yayin_olur(tmp_path):
    """release.yml yolu: etiket push'u iş akışını tetikler, etiket HEAD'dedir."""
    kok, kayit, bin_dizin, head = _yayin_tezgahi(tmp_path)
    (kayit / "cevap_ref.txt").write_text(f"commit\t{head}\n", encoding="utf-8")
    sonuc = _kostur(kok, bin_dizin)

    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert _hedef(_yayin_cagrisi(kayit)) == head


def test_yayin1_aciklamali_etiket_commite_soyulur(tmp_path):
    """Açıklamalı etiketin nesnesi etiket nesnesidir; karşılaştırma commit'le."""
    kok, kayit, bin_dizin, head = _yayin_tezgahi(tmp_path)
    (kayit / "cevap_ref.txt").write_text(f"tag\t{SHA_A}\n", encoding="utf-8")
    (kayit / "cevap_tag.txt").write_text(f"commit\t{head}\n", encoding="utf-8")
    assert _kostur(kok, bin_dizin).returncode == 0
    assert any(c[:1] == ["api"] and c[1].endswith("/git/tags/" + SHA_A)
               for c in _gh_cagrilari(kayit))

    kok2, kayit2, bin2, _ = _yayin_tezgahi(tmp_path / "ikinci")
    (kayit2 / "cevap_ref.txt").write_text(f"tag\t{SHA_A}\n", encoding="utf-8")
    (kayit2 / "cevap_tag.txt").write_text(f"commit\t{SHA_B}\n", encoding="utf-8")
    sonuc = _kostur(kok2, bin2)
    assert sonuc.returncode != 0
    assert _yayin_cagrisi(kayit2) is None


def test_yayin1_etiket_olcumu_basarisizsa_yayin_yok(tmp_path):
    """Ağ/yetki hatası 'etiket yok' sayılmaz (fail-closed)."""
    kok, kayit, bin_dizin, _ = _yayin_tezgahi(tmp_path)
    (kayit / "api_cikis.txt").write_text("1", encoding="utf-8")
    sonuc = _kostur(kok, bin_dizin)

    assert sonuc.returncode != 0
    assert _yayin_cagrisi(kayit) is None
    assert "ölçülemedi" in sonuc.stdout


def test_yayin1_kapidan_sonra_head_degisirse_yayin_yok(tmp_path):
    """Kapı ~15 dk sürer; arada commit atılırsa doğrulanan commit yayınlanmaz."""
    kapi = ('git -C "$(dirname "$0")/.." -c core.hooksPath=/dev/null '
            '-c commit.gpgsign=false -c user.name=s -c user.email=s@s.invalid '
            'commit -q --allow-empty -m "kapı sırasında commit"\nexit 0\n')
    kok, kayit, bin_dizin, head = _yayin_tezgahi(tmp_path, kapi_govdesi=kapi)
    sonuc = _kostur(kok, bin_dizin)

    assert _git(kok, "rev-parse", "HEAD") != head, "fikstür HEAD'i değiştiremedi"
    assert sonuc.returncode != 0, sonuc.stdout
    assert _yayin_cagrisi(kayit) is None
    assert "kapıdan sonra değişti" in sonuc.stdout


def test_yayin1_taslak_yolu_da_etiketi_shaya_baglar(tmp_path):
    """release.yml'nin TASLAK yolu (kapı atlamalı) da aynı SHA kuralına tabi."""
    kok, kayit, bin_dizin, head = _yayin_tezgahi(tmp_path)
    ortam_betigi = tmp_path / "taslak.sh"
    ortam_betigi.write_text(
        "TASLAK=1 KAPIYI_ATLA=1 "
        "KAPIYI_ATLA_GEREKCE='CI runner: kapının tamamı burada koşamaz' "
        f'bash "{kok}/packaging/publish_release.sh"\n', encoding="utf-8")
    sonuc = _kostur(kok, bin_dizin, betik=ortam_betigi)

    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    argumanlar = _yayin_cagrisi(kayit)
    assert "--draft" in argumanlar
    assert _hedef(argumanlar) == head


# ---------------------------------------------------------------------------
# YAYIN-2 — release_gate.sh 4/10
# ---------------------------------------------------------------------------

def _kapi_metni():
    return KAPI_BETIGI.read_text(encoding="utf-8")


def _bash_fonksiyonu(metin, ad):
    """``ad() { ... }`` gövdesini kaynak dosyadan çıkarır (kopyalamaz)."""
    satirlar = metin.splitlines()
    bas = next((i for i, s in enumerate(satirlar)
                if re.match(r"^%s\s*\(\)\s*\{" % re.escape(ad), s)), None)
    assert bas is not None, "%s() kapı betiğinde yok" % ad
    for j in range(bas + 1, len(satirlar)):
        if satirlar[j] == "}":
            return "\n".join(satirlar[bas:j + 1])
    raise AssertionError("%s() gövdesinin sonu bulunamadı" % ad)


def _yardimcilar(metin):
    """Kapının rapor işlevlerini (basarili/basarisiz/bilgi) olduğu gibi alır."""
    satirlar = [s for s in metin.splitlines()
                if re.match(r"^(basarili|basarisiz|atlandi|bilgi)\s*\(\)", s)]
    assert len(satirlar) == 4, satirlar
    return satirlar


def _bash(betik):
    p = subprocess.run(["bash", "-c", betik], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, "kabuk hatası: %s" % p.stderr
    return p.stdout


def _degerlendir(satirlar, sha=SHA_A):
    """``ci_kosulari_degerlendir`` işlevini fikstürle koşturur.

    Çıktı: (GEÇTİ satırları, KALDI satırları, BİLGİ satırları, HATA_SAYISI)
    """
    metin = _kapi_metni()
    tsv = "\n".join("\t".join(s) for s in satirlar)
    betik = "\n".join(
        ["set -uo pipefail", "KIRMIZI=''; YESIL=''; SARI=''; SIFIR=''",
         "HATA_SAYISI=0"]
        + _yardimcilar(metin)
        + [_bash_fonksiyonu(metin, "ci_kosulari_degerlendir"),
           "TSV=$(cat <<'FIKSTUR'\n%s\nFIKSTUR\n)" % tsv,
           'ci_kosulari_degerlendir "%s" "$TSV"' % sha,
           'echo "HATA_SAYISI=$HATA_SAYISI"'])
    cikti = _bash(betik)
    gecti = [s for s in cikti.splitlines() if "GEÇTİ" in s]
    kaldi = [s for s in cikti.splitlines() if "KALDI" in s]
    bilgi = [s for s in cikti.splitlines() if "BİLGİ" in s]
    hata = int(re.search(r"HATA_SAYISI=(\d+)", cikti).group(1))
    return gecti, kaldi, bilgi, hata


# gh run list --json conclusion,status,workflowName,headSha
#   --jq '.[] | [.workflowName, .status, (.conclusion // "-"), .headSha] | @tsv'
# çıktısının satırları. Gerçek biçim v3.0.5 SHA'sının koşularından alındı
# (kanıt: gh_run_list_v305_0a138ff6a.tsv); süren koşuda conclusion boştur
# ve jq '-' basar.
KOSU_YESIL = ("tests", "completed", "success", SHA_A)
KOSU_SUREN = ("tests", "in_progress", "-", SHA_A)
KOSU_SIRADA = ("tests", "queued", "-", SHA_A)
KOSU_DUSEN = ("tests", "completed", "failure", SHA_A)
KOSU_IPTAL = ("tests", "completed", "cancelled", SHA_A)
KOSU_RELEASE_SUREN = ("release", "in_progress", "-", SHA_A)
KOSU_RELEASE_ATLANDI = ("release", "completed", "skipped", SHA_A)


def test_yayin2_yesil_ve_suren_kopya_beklenmez():
    """28 Eki 19:40 durumu: aday koşusu yeşil, main push koşusu sürüyor."""
    gecti, kaldi, bilgi, hata = _degerlendir([KOSU_SUREN, KOSU_YESIL])
    assert hata == 0 and not kaldi, kaldi
    assert len(gecti) == 1 and "yeşil" in gecti[0]
    assert len(bilgi) == 1 and "kopya" in bilgi[0]


def test_yayin2_sirada_bekleyen_kopya_da_beklenmez():
    gecti, kaldi, bilgi, hata = _degerlendir([KOSU_YESIL, KOSU_SIRADA])
    assert hata == 0 and len(gecti) == 1 and len(bilgi) == 1


def test_yayin2_yalniz_suren_tests_kaldi():
    """Yeşil kanıt yoksa süren 'tests' eskisi gibi beklenir."""
    gecti, kaldi, bilgi, hata = _degerlendir([KOSU_SUREN])
    assert hata == 1 and not gecti and not bilgi
    assert "hâlâ koşuyor" in kaldi[0]


def test_yayin2_basarisiz_kopya_yesile_ragmen_kaldi():
    gecti, kaldi, _bilgi, hata = _degerlendir([KOSU_YESIL, KOSU_DUSEN])
    assert hata == 1 and any("başarısız" in s and "failure" in s for s in kaldi)


def test_yayin2_iptal_edilmis_kopya_yesile_ragmen_kaldi():
    """İptal edilen koşu kopya kuralına girmez (yalnız SÜREN kopya girer)."""
    _gecti, kaldi, bilgi, hata = _degerlendir([KOSU_IPTAL, KOSU_YESIL])
    assert hata == 1 and not bilgi
    assert any("cancelled" in s for s in kaldi)


def test_yayin2_tests_disindaki_suren_akis_kaldi():
    """Kural yalnız aynı iş akışının kopyası için: release süreni beklenir."""
    _gecti, kaldi, bilgi, hata = _degerlendir([KOSU_YESIL, KOSU_RELEASE_SUREN])
    assert hata == 1 and not bilgi
    assert "release" in kaldi[0] and "hâlâ koşuyor" in kaldi[0]


def test_yayin2_baska_shadaki_yesil_kanit_sayilmaz():
    """Yeşil koşu başka SHA'ya aitse süren kopya beklenir (ve SHA KALDI)."""
    baska_yesil = ("tests", "completed", "success", SHA_B)
    gecti, kaldi, bilgi, hata = _degerlendir([baska_yesil, KOSU_SUREN])
    assert not gecti and not bilgi
    assert hata == 2
    assert any("farklı SHA" in s for s in kaldi)
    assert any("hâlâ koşuyor" in s for s in kaldi)


def test_yayin2_atlanan_akis_ve_iki_yesil_gecer():
    """v3.0.5 yayın anındaki gerçek küme: iki yeşil 'tests' (aday + main)."""
    gecti, kaldi, bilgi, hata = _degerlendir([KOSU_YESIL, KOSU_YESIL, KOSU_RELEASE_ATLANDI])
    assert hata == 0 and len(gecti) == 1 and not bilgi and not kaldi


def test_yayin2_kapi_bolumu_islevi_gh_ciktisiyla_cagiriyor(tmp_path):
    """4/10 bölümünün TAMAMI (gh çağrısı dahil) vekil gh ile koşar.

    Vekil ``gh`` bir kabuk işlevidir (``command -v gh`` onu bulur) ve
    gerçek gh'nin --jq sonrası TSV çıktısını basar; çağrı argümanları da
    kaydedilir: bu SHA'nın BÜTÜN koşuları istenmeli.
    """
    metin = _kapi_metni()
    bas = metin.index('baslik "4/10')
    son = metin.index('baslik "5/10')
    bolum = metin[metin.index("\n", bas) + 1:son]
    argumanlar = tmp_path / "gh_args.txt"
    tsv = "\n".join("\t".join(s) for s in (KOSU_SUREN, KOSU_YESIL))
    betik = "\n".join(
        ["set -uo pipefail", "KIRMIZI=''; YESIL=''; SARI=''; SIFIR=''",
         "HATA_SAYISI=0", "YEREL='%s'" % SHA_A]
        + _yardimcilar(metin)
        + ['gh() { printf "%%s\\n" "$@" > "%s"; cat <<\'FIKSTUR\'\n%s\nFIKSTUR\n}'
           % (argumanlar, tsv),
           bolum, 'echo "HATA_SAYISI=$HATA_SAYISI"'])
    cikti = _bash(betik)
    assert "HATA_SAYISI=0" in cikti, cikti
    assert "BİLGİ" in cikti and "GEÇTİ" in cikti
    cagri = argumanlar.read_text(encoding="utf-8").splitlines()
    assert cagri[:4] == ["run", "list", "--commit", SHA_A], cagri
    assert "--limit" in cagri and cagri[cagri.index("--limit") + 1] != "1"
