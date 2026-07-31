"""Bulgu kayıt defterinin kendisinin bekçisi.

``docs/BULGU_KAYIT_DEFTERI.md`` kapatılan her kusuru bir bekçi teste bağlar.
O defterin değeri tamamen şu iddiaya dayanır:

    "Bu kusur geri gelirse şu test kırılır."

İddia doğrulanmazsa defter, güven veren ama karşılığı olmayan bir belgeye
dönüşür — yani tam olarak bu sürümde kapattığımız hata sınıfının kendisi
olur: iki parça (defter ve test takımı) tek başına doğru görünür, aradaki
sözleşme yanlıştır.

Bu dosya o sözleşmeyi mekanik kılar:

* Defterde adı geçen her test DOSYASI var mı?
* Defterde adı geçen her test FONKSİYONU o dosyada gerçekten tanımlı mı?

Bir bekçi yeniden adlandırılır ya da silinirse defter sessizce eskimez;
burası kırılır.

Not: bu test bekçilerin doğru şeyi ölçtüğünü kanıtlamaz — onu ancak
bekçilerin kendi negatif kontrolleri gösterir. Burada kanıtlanan şey daha
dar ama vazgeçilmez: defterin işaret ettiği yer BOŞ DEĞİL.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'docs' / 'BULGU_KAYIT_DEFTERI.md'
TESTS_DIR = ROOT / 'tests'

#: Defterde `test_x.py::test_y` ya da yalnız `test_x.py` biçiminde geçen
#: bekçi atıfları. Tablo hücrelerinde ters tırnak içinde yazılırlar.
_REFERENCE = re.compile(r'`(test_[\w/]+\.py)(?:::([\w:]+))?`')


def _references():
    text = REGISTRY.read_text(encoding='utf-8')
    seen = []
    for match in _REFERENCE.finditer(text):
        seen.append((match.group(1), match.group(2)))
    return seen


def test_registry_exists_and_is_not_empty():
    """Defter silinirse ya da boşalırsa bakım altyapısı kaybolur."""
    assert REGISTRY.is_file(), f'{REGISTRY} yok'
    assert len(REGISTRY.read_text(encoding='utf-8')) > 2000, (
        'Bulgu kayıt defteri anlamlı içerik taşımıyor')


def test_registry_references_at_least_the_known_guards():
    """Defter gerçekten bekçilere atıf yapmalı (boş tablo geçmesin)."""
    refs = _references()
    assert len(refs) >= 15, (
        f'Defterde yalnız {len(refs)} bekçi atfı var; kapatılan bulgular '
        f'bekçilerine bağlanmamış olabilir.')


@pytest.mark.parametrize('filename,funcname', _references())
def test_referenced_guard_exists(filename, funcname):
    """Defterde adı geçen bekçi dosyası ve fonksiyonu gerçekten var mı?

    Bu testin kırılması iki şeyden birini gösterir:
      1. Bekçi silinmiş/yeniden adlandırılmış ve defter güncellenmemiş
         (defter artık yalan söylüyor), ya da
      2. Deftere hiç yazılmamış bir test adı yazılmış (yazım hatası).
    İkisi de sessiz kalmamalı.
    """
    path = TESTS_DIR / pathlib.PurePath(filename).name
    assert path.is_file(), (
        f'Bulgu kayıt defteri {filename} dosyasına atıf yapıyor ama dosya '
        f'yok. Bekçi silindiyse defterdeki satır da güncellenmeli.')
    if not funcname:
        return
    # 'Sinif::fonksiyon' biçimi de kabul edilir; son parça aranan addır.
    leaf = funcname.split('::')[-1]
    # Parametreli testlerde ad `test_x[param]` olarak koşar; tanım sade addır.
    leaf = leaf.split('[')[0]
    source = path.read_text(encoding='utf-8')
    # Defter yalnız test fonksiyonlarına değil, bekçinin gerekçeli
    # listelerine de atıf yapar (ör. DECLARED_UNMODELLED). Bu listeler
    # bekçinin sözleşmesinin parçasıdır: silinirlerse bekçi sessizce
    # her şeyi meşru saymaya başlar. Bu yüzden modül düzeyi sabitler de
    # geçerli atıf kabul edilir, ama VARLIKLARI aynı şekilde doğrulanır.
    patterns = (
        rf'^\s*def {re.escape(leaf)}\s*\(',      # fonksiyon tanımı
        rf'^\s*class {re.escape(leaf)}\b',       # sınıf tanımı
        rf'^{re.escape(leaf)}\s*[:=]',           # modül düzeyi sabit
    )
    assert any(re.search(p, source, re.M) for p in patterns), (
        f'{filename} içinde `{leaf}` diye bir tanım yok. Bekçi yeniden '
        f'adlandırıldıysa defterdeki satır da güncellenmeli.')


def test_open_debt_section_is_present():
    """Açık borç bölümü kaldırılmamalı.

    "Kapatılanlar" listesi tek başına yanıltıcıdır: neyin BİLEREK açık
    bırakıldığı da kayıtlı olmalı, yoksa açık kalem zamanla unutulur ve
    bir sonraki denetimde "yeni bulgu" diye geri gelir.
    """
    text = REGISTRY.read_text(encoding='utf-8')
    assert '## Açık borç' in text, (
        'Defterdeki "Açık borç" bölümü kaldırılmış; bilerek açık bırakılan '
        'kalemlerin kaydı olmadan defter eksiktir.')
