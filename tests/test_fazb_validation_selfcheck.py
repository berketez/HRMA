# -*- coding: utf-8 -*-
"""ÖH FAZ F / F3 — `data/validation/selfcheck.py` artık CI'da ATEŞLENİYOR.

NEDEN BU DOSYA VAR (defter P13B3-04)
------------------------------------
`data/validation/` altındaki 20 kayıt, kampanyanın fizik dalgasının ÖLÇÜM
ÇAPASIdır: Bartz hata bandı, iki-faz parçacık yükü kaybı, Lamé kalın cidar
çözümü, izentropik alan-Mach bağıntısı… Bu kayıtların doğruluğunu denetleyen
bir betik depoda DURUYOR (`selfcheck.py`, 640 satır, 14 kaydı kendi
bağıntısından yeniden türetiyor) — ama hiçbir yerden ÇAĞRILMIYORDU:

  * `pytest.ini` `testpaths = tests` diyor; betik `data/validation` altında,
    yani `pytest` onu hiç toplamıyor.
  * Hiçbir iş akışı adımı `python data/validation/selfcheck.py` koşmuyor.
  * Depoda betiği ithal eden ya da çağıran tek bir dosya yok (ölçüldü).

Yani doğrulama veri kümesinin bekçisi vardı, ama bekçi hiç uyandırılmıyordu.
Bir kayıt sessizce bozulsa (birim hatası, kopyalama sırasında kayan basamak,
"beklenen değer"in elle düzeltilmesi) kimse görmezdi — üstelik o kayıtlar
fizik onarımının doğru/yanlış ölçütüdür.

BU SARMALAYICININ İŞİ
---------------------
`selfcheck.main()` fonksiyonunu pytest içinden çağırmak. Dosya `tests/`
altında olduğu için CI ana işi (`pytest tests/`) onu otomatik koşturur;
aşağıdaki üçüncü bekçi de o koşumun sessizce dışarıda bırakılamayacağını
kilitler. `pytest.ini` DEĞİŞTİRİLMEDİ — betik hâlâ elle de koşulabilir:

    python3 data/validation/selfcheck.py

ÖLÇÜM (27 Ağustos 2026, HEAD baa9d9e):
    kayıt: 20 · yeniden türetilen: 14 · yalnız ölçüm: 6   -> çıkış kodu 0
"""

import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest

DEPO = Path(__file__).resolve().parents[1]
SELFCHECK = DEPO / "data" / "validation" / "selfcheck.py"
KAYIT_DIZINI = DEPO / "data" / "validation"
ISAKISI_DIZINI = DEPO / ".github" / "workflows"

#: 27 Ağustos 2026 ölçümü — kayıt sayısı ve yeniden türetme kapsamı.
#: Bunlar ALT SINIRDIR: kapsam büyüyebilir, sessizce KÜÇÜLEMEZ. Bir kaydın
#: `MEASUREMENT_ONLY`ye taşınması yeniden türetmeyi kapatır ve bu bekçi
#: kırmızıya döner — "artık türetilemiyor" kararı görünür olmalıdır.
KAYIT_TABANI = 20
YENIDEN_TURETME_TABANI = 14


def _selfcheck_yukle():
    """Betiği HER ÇAĞRIDA taze bir modül olarak yükler.

    Taze olması şart: `selfcheck` bulguları modül düzeyindeki `_findings`
    listesinde biriktirir; aynı modül iki kez çağrılsa ikinci koşum birinci
    koşumun bulgularını da rapor ederdi.
    """
    spec = importlib.util.spec_from_file_location(
        "hrma_validation_selfcheck_lab", SELFCHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # sys.modules'a KONMAZ (taze kalır)
    return mod


def test_selfcheck_betigi_yerinde():
    """Sarmalayıcı, olmayan bir betiği sararak yeşil kalmasın."""
    assert SELFCHECK.is_file(), (
        f"{SELFCHECK} yok — doğrulama veri kümesinin bekçisi kaybolmuş")


def test_dogrulama_kayitlari_kendi_baginitilarindan_uretiliyor(capsys):
    """F3: betik GERÇEKTEN koşar ve bugün temizdir (çıkış kodu 0)."""
    mod = _selfcheck_yukle()
    kod = mod.main([])
    cikti = capsys.readouterr().out
    assert kod == 0, (
        "data/validation kayıtları kendi bağıntılarından yeniden "
        f"üretilemiyor (çıkış kodu {kod}). Betik çıktısı:\n{cikti}")
    assert "temiz" in cikti, (
        f"selfcheck 0 döndü ama 'temiz' demedi — çıktı:\n{cikti}")


def test_yeniden_turetme_kapsami_sessizce_kucultulemez():
    """Kapsam çürümesi bekçisi: 20 kayıt / 14 yeniden türetme ALT SINIR.

    Bir kaydı `MEASUREMENT_ONLY` kümesine taşımak, o kaydın sayısını
    "tanık"tan "kaynak"a terfi ettirir — yani bir daha hiçbir bağıntıyla
    sınanmaz. Bu meşru bir karar olabilir (ölçüme dayanan kayıtlar için
    zaten öyle), ama SESSİZ olamaz.
    """
    mod = _selfcheck_yukle()
    kayitlar = sorted(KAYIT_DIZINI.glob("*.json"))
    assert len(kayitlar) >= KAYIT_TABANI, (
        f"data/validation'da {len(kayitlar)} kayıt var; 27 Ağustos 2026 "
        f"ölçümü {KAYIT_TABANI} idi — kayıt silinmiş olabilir")
    assert len(mod.DERIVATION_CHECKS) >= YENIDEN_TURETME_TABANI, (
        f"yeniden türetilen kayıt sayısı {len(mod.DERIVATION_CHECKS)}; "
        f"ölçüm {YENIDEN_TURETME_TABANI} idi — bir kayıt sessizce "
        "'yalnız ölçüm' sınıfına kaymış olabilir")

    # Her kaydın bir sınıfı olmalı: ya yeniden türetilir ya ölçümdür.
    sinifsiz = [k.stem for k in kayitlar
                if k.stem not in mod.DERIVATION_CHECKS
                and k.stem not in mod.MEASUREMENT_ONLY]
    assert not sinifsiz, (
        f"şu kayıtlar hiçbir sınıfta değil: {sinifsiz} — selfcheck onları "
        "bulgu olarak işaretler, ama sınıflandırma kararı burada da görünür "
        "olmalı")


def test_selfcheck_bozuk_bir_sayiyi_gercekten_goruyor(tmp_path, capsys):
    """MUTASYON KANITI — bekçi, kusuru GÖRDÜĞÜ gösterilmedikçe 'var' sayılmaz.

    Betiğin 0 döndürmesi tek başına hiçbir şey kanıtlamaz: hiç denetim
    yapmayan bir betik de 0 döner. Bu yüzden kayıt kümesinin BELLEKTEKİ bir
    kopyası bozulur (Lamé teğetsel gerilmesi %5 kaydırılır) ve betiğin bunu
    kırmızıya çevirdiği ölçülür. Depo dosyalarına YAZILMAZ: `HERE` geçici
    dizine yönlendirilir.
    """
    for kayit in KAYIT_DIZINI.glob("*.json"):
        shutil.copy2(kayit, tmp_path / kayit.name)

    kurban = tmp_path / "structural_lame_thick_cylinder_si.json"
    veri = json.loads(kurban.read_text(encoding="utf-8"))
    alan = veri["expected_outputs"]["tangential_stress_pa"]
    anahtar = "r_0.10m"
    onceki = alan[anahtar]
    alan[anahtar] = onceki * 1.05                      # %5 kaydırma
    kurban.write_text(json.dumps(veri, ensure_ascii=False, indent=1),
                      encoding="utf-8")

    mod = _selfcheck_yukle()
    mod.HERE = str(tmp_path)
    kod = mod.main([])
    cikti = capsys.readouterr().out

    assert kod == 1, (
        f"Lamé teğetsel gerilmesi {onceki} -> {alan[anahtar]} kaydırıldı ama "
        f"selfcheck {kod} döndü. Bu betik bir sayının bozulduğunu GÖREMİYOR; "
        f"'temiz' hükmü dayanaksız. Çıktı:\n{cikti}")
    assert "structural_lame_thick_cylinder_si" in cikti, (
        "selfcheck kırmızı verdi ama bozulan kaydın adını söylemedi — "
        f"bulgu adressiz. Çıktı:\n{cikti}")


def test_ci_ana_isi_tests_dizininin_TAMAMINI_kosuyor():
    """F3 kilidi: bu sarmalayıcı CI'dan sessizce çıkarılamaz.

    Sarmalayıcı yalnızca CI ana işi `tests/` dizininin TAMAMINI koştuğu
    sürece ateşlenir. Komut bir gün dosya listesine dönüşürse (ya da bu
    dosya listeden düşerse) selfcheck yine hiç koşmayan bir betiğe döner —
    tam olarak P13B3-04'ün durumu. O yüzden dizin-kapsamı burada kilitli.
    """
    yaml = pytest.importorskip(
        "yaml", reason="PyYAML kurulu değil — derin YAML denetimi atlandı")
    veri = yaml.safe_load(
        (ISAKISI_DIZINI / "tests.yml").read_text(encoding="utf-8"))
    adimlar = veri["jobs"]["pytest"]["steps"]
    komutlar = "\n".join(a.get("run", "") for a in adimlar)

    assert re.search(r"^\s*pytest\s+tests/\s", komutlar, re.M), (
        "CI ana işi `pytest tests/` (dizinin tamamı) koşmuyor — bu "
        "sarmalayıcının koştuğu garanti değil. Bulunan komutlar:\n"
        f"{komutlar}")

    # Bu dosya gerçekten o dizinde mi? (Sarmalayıcı taşınırsa kilit boşa çıkar.)
    assert Path(__file__).resolve().parent == (DEPO / "tests"), (
        "sarmalayıcı tests/ dışına taşınmış — CI kapsamı kilidi anlamsızlaştı")
