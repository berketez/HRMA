"""Geçici dizin temizliğinin çalışma dizinini silememesi (v2.6.26 bekçisi).

Kapatılan kusur — 31 Temmuz 2026'da ÜÇ KEZ yaşandı:

    shutil.rmtree(os.path.dirname(main_stl_path), ignore_errors=True)

`main_stl_path` göreli bir yol olduğunda (`./motor.stl`) `os.path.dirname`
`"."` döndürür ve `rmtree(".")` **çalışma dizininin tamamını** siler. Test
takımı STL dışa aktarımına dokunduğu anda depo kökü uçuyordu; üç ayrı
konumda (`/Users/apple/HRMA` iki kez, `~/Projects/HRMA-v2626` bir kez)
ağaç pytest ortasında yok oldu ve suite `FileNotFoundError` ile düştü.

`ignore_errors=True` durumu daha da sinsi yapıyordu: silme başarısız olsa
bile hiçbir uyarı çıkmıyordu.

Kural: bir temizlik çağrısı YALNIZ kendi ürettiği geçici dizini silebilir.
Silinecek yol hem `tempfile.gettempdir()` altında olmalı hem de bu modülün
kendi önekini (`hrma_stl_`) taşımalıdır.
"""

import ast
import pathlib
import re

import pytest

KOK = pathlib.Path(__file__).resolve().parent.parent
HEDEFLER = [
    KOK / "hrma/app.py",
    KOK / "hrma/export/cad_visualization.py",
]


def _kaynaklar():
    for p in HEDEFLER:
        if p.exists():
            yield p, p.read_text(encoding="utf-8")


def _rmtree_cagrilari(kaynak):
    """AST ile GERÇEK rmtree çağrılarını döndürür (yorum/docstring sayılmaz)."""
    bulunan = []
    for d in ast.walk(ast.parse(kaynak)):
        if not isinstance(d, ast.Call):
            continue
        f = d.func
        ad = f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', '')
        if ad != 'rmtree':
            continue
        bulunan.append(d)
    return bulunan


def _ilk_arg_dirname_mi(cagri):
    if not cagri.args:
        return False
    a = cagri.args[0]
    return (isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute)
            and a.func.attr == 'dirname')


class TestKorumasizSilmeYok:
    def test_dirname_dogrudan_rmtree_edilmez(self):
        """`rmtree(os.path.dirname(...))` GERÇEK çağrısı geri gelirse kırılır.

        Metinsel arama yerine AST: açıklama yorumları ve docstring'ler
        kodla karıştırılmaz (ilk sürüm tam bu yüzden yanlış alarm verdi).
        """
        for p, s in _kaynaklar():
            for cagri in _rmtree_cagrilari(s):
                assert not _ilk_arg_dirname_mi(cagri), (
                    f"{p.name}:{cagri.lineno} rmtree(os.path.dirname(...)) "
                    f'korumasiz — goreli yolda dirname "." doner ve calisma '
                    f"dizini silinir"
                )

    def test_her_rmtree_bir_tempdir_kapisiyla_korunur(self):
        """Her `rmtree` çağrısının yakınında tempdir doğrulaması olmalı."""
        for p, s in _kaynaklar():
            satirlar = s.splitlines()
            for cagri in _rmtree_cagrilari(s):
                i = cagri.lineno - 1
                satir = satirlar[i]
                pencere = "\n".join(satirlar[max(0, i - 14):i + 2])
                assert "gettempdir" in pencere or "hrma_stl_" in pencere, (
                    f"{p.name}:{i + 1} rmtree cagrisinin yakininda tempdir "
                    f"kapisi yok:\n    {satir.strip()}"
                )

    def test_rmtree_nokta_veya_bos_yola_yazilmaz(self):
        yasak = re.compile(r"""rmtree\(\s*['"](\.|\.\/|)['"]""")
        for p, s in _kaynaklar():
            assert not yasak.search(s), f"{p.name}: rmtree('.') / rmtree('')"


class TestKaynakDerlenebilir:
    def test_hedefler_ayristirilabilir(self):
        for p, s in _kaynaklar():
            ast.parse(s)


class TestGuvenliSilmeDavranisi:
    """Kapının kendisi doğru mu — gerçek dizinlerle sınanır (silme YOK)."""

    @staticmethod
    def _silinebilir_mi(yol):
        import os
        import tempfile
        d = os.path.dirname(os.path.abspath(yol))
        tmp = os.path.realpath(tempfile.gettempdir())
        return (os.path.realpath(d).startswith(tmp)
                and os.path.basename(d).startswith("hrma_stl_"))

    def test_gecici_dizin_silinebilir(self, tmp_path):
        import os
        import tempfile
        d = tempfile.mkdtemp(prefix="hrma_stl_")
        try:
            assert self._silinebilir_mi(os.path.join(d, "motor.stl"))
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    @pytest.mark.parametrize("yol", [
        "./motor.stl",          # asıl vaka: dirname -> "."
        "motor.stl",            # dirname -> ""
        "cad_exports/a.stl",    # depo içi
        "/Users/apple/HRMA/x.stl",
    ])
    def test_depo_ici_yollar_silinemez(self, yol):
        assert not self._silinebilir_mi(yol), yol

    def test_tempdir_altinda_ama_yanlis_onek_silinemez(self):
        import os
        import tempfile
        d = tempfile.mkdtemp(prefix="baska_")
        try:
            assert not self._silinebilir_mi(os.path.join(d, "motor.stl"))
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
