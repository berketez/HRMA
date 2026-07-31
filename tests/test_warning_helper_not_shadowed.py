"""Uyarı üreticisi ``_w`` hiçbir fonksiyonda gölgelenmemeli.

v2.6.26'da bulunan UYUYAN hata: ``solid_rocket_engine.calculate_performance``
içinde bir yerde ``_n, _w, _d, ... = self._finocyl_params()`` yazıyordu.
Buradaki ``_w`` "genişlik" demekti ama Python yerel değişkenleri STATİK
belirler: o satır hiç çalışmasa bile (BATES grain'de finocyl dalına
girilmez) ``_w`` fonksiyonun tamamında yerel sayılır ve aynı fonksiyondaki
her ``_w(...)`` uyarı çağrısı ``UnboundLocalError`` verir.

Hata aylarca sessiz kaldı çünkü fonksiyondaki mevcut ``_w(...)`` çağrıları
yalnız hata dallarındaydı. v2.6.26'da web/dış çap tutarlılık kontrolü
eklenince normal akışa girdi ve geçerli bir istek HTTP 400 döndürmeye
başladı — üstelik hata mesajı kullanıcıya "cannot access local variable"
diyordu.

Bu test o sınıfın tamamını kapatır: modül düzeyinde ``_w`` tanımlayan her
dosyada, hiçbir fonksiyon ``_w`` adını yeniden bağlayamaz.
"""

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = '_w'


def _modules_defining_helper():
    """Modul duzeyinde `_w` tanimlayan .py dosyalari."""
    found = []
    for path in sorted((ROOT / 'hrma').rglob('*.py')):
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError:                        # pragma: no cover
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == HELPER:
                found.append((path, tree))
                break
    return found


def _rebindings(tree):
    """Fonksiyon govdelerinde `_w` adini yeniden baglayan satirlar."""
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == HELPER:
            continue
        for sub in ast.walk(node):
            targets = []
            if isinstance(sub, ast.Assign):
                targets = sub.targets
            elif isinstance(sub, (ast.For, ast.AsyncFor)):
                targets = [sub.target]
            elif isinstance(sub, ast.comprehension):
                targets = [sub.target]
            elif isinstance(sub, ast.NamedExpr):
                targets = [sub.target]
            elif isinstance(sub, ast.withitem) and sub.optional_vars:
                targets = [sub.optional_vars]
            for target in targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name) and name.id == HELPER:
                        hits.append((node.name, name.lineno))
    return hits


def test_helper_modules_are_found():
    """Test kendini kandirmasin: en az bir modul bulunmali."""
    assert _modules_defining_helper(), (
        '_w tanimlayan modul bulunamadi - test artik bir sey olcmuyor'
    )


@pytest.mark.parametrize('path,tree', _modules_defining_helper(),
                         ids=lambda v: v.name if hasattr(v, 'name') else '')
def test_warning_helper_is_never_rebound(path, tree):
    hits = _rebindings(tree)
    assert not hits, (
        f'{path.relative_to(ROOT)}: su fonksiyonlar `_w` adini yeniden '
        f'bagliyor ve modul duzeyindeki uyari ureticisini golgeliyor '
        f'(o dala hic girilmese bile UnboundLocalError uretir): '
        + ', '.join(f'{fn} (satir {line})' for fn, line in hits)
        + '. Yerel degisken adini degistirin (or. _wid).')
