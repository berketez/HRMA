"""docs/ kanıtını kapı DIŞINDA okuyan test kodunun statik tarayıcısı — ÖH D36 kanit-atlama.

Yalnız standart kütüphane; pytest İTHAL ETMEZ. İki kullanıcısı var:
``tests/test_kanit_atlama_kapisi.py`` (bekçi) ve
``packaging/yayin_dali_uret.sh`` (yayın dalı dedektörü, kuru koşu).

NE ARAR
-------
Bir *tohum*, test kodunda (docstring ve yalnız-dize ifadeleri hariç) docs/
kanıt ağacını gösteren değerdir:

* ``'docs/scofield/...'`` biçiminde bir dize sabiti (``docs/arastirma``,
  ``docs/tasarim``, ``docs/kabul`` dahil),
* ``os.path.join(KOK, 'docs', 'scofield', ...)`` / ``KOK / 'docs' / 'scofield'``
  gibi parça dizisi,
* ``kanit_yolu(...)`` çağrısı.

Tohumdan türeyen değer (atama, ``/``, ``os.path.join``, ``str``, f-dize,
``.parent`` ...) *kirli*dir. Kirli bir değer ``kanit_gerekli(...)`` kapısından
(ya da yazılan çıktı için ``kanit_cikti(...)``) geçmeden bir *çukura* — ``open``, ``.read_text()``, ``.exists()``,
``json.load``, ``subprocess.run([... 'node' ...])``, yerel okuma yardımcısı,
``return`` ... kısacası G/Ç yapabilecek HERHANGİ bir kullanıma — akarsa
**ihlal**dir. Zararsız kullanımlar ihlal sayılmaz: iddia/atlama mesajı,
karşılaştırma (``in``, ``==``), ``.name``/``.stem`` gibi ad bilgisi,
``startswith``/``endswith``.

Bilinçli sınır: veri içinden gelen dinamik yol (ör. bir sözlüğün ``'kanit'``
alanı) tohum değildir; o tür okumalar elle kapıya bağlanır.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

HARIC = ('docs/scofield', 'docs/arastirma', 'docs/tasarim', 'docs/kabul')
_ALT = frozenset(h.split('/', 1)[1] for h in HARIC)
_DIZE = re.compile(r'(?:^|[/\\])docs[/\\](?:%s)(?:[/\\]|$)'
                   % '|'.join(sorted(_ALT)))
#: Kanıt dizinindeki bir Python modülünün İTHALİ (``from docs.scofield... import``).
_MODUL = re.compile(r'^docs\.(?:%s)(?:\.|$)' % '|'.join(sorted(_ALT)))

#: Kapılar: okunacak kanıt (``kanit_gerekli``) ve kanıt dizinine YAZILACAK
#: çıktı (``kanit_cikti`` — üst dizini gerekli kılar).
KAPILAR = frozenset({'kanit_gerekli', 'kanit_cikti'})
COZUCU = 'kanit_yolu'

#: Kirliliği TAŞIYAN çağrılar (sonuç yine bir yoldur).
_YAYAN_CAGRILAR = frozenset({
    'os.path.join', 'os.path.abspath', 'os.path.normpath', 'os.path.realpath',
    'os.path.dirname', 'os.fspath', 'pathlib.Path', 'Path', 'pathlib.PurePath',
    'PurePath', 'str',
})
_YAYAN_YONTEMLER = frozenset({
    'joinpath', 'with_suffix', 'with_name', 'with_stem', 'resolve', 'absolute',
})
_YAYAN_NITELIKLER = frozenset({'parent'})
#: Yalnız ad bilgisi — G/Ç değil.
_AD_NITELIKLERI = frozenset({'name', 'stem', 'suffix', 'suffixes', 'parts'})
#: Dize karşılaştırma yöntemleri — G/Ç değil.
_KARSILASTIRMA_YONTEMLERI = frozenset({'startswith', 'endswith'})
#: Argümanları MESAJ olan çağrılar.
_MESAJ_CAGRILARI = frozenset({
    'pytest.skip', 'pytest.fail', 'pytest.xfail', 'pytest.exit', 'print',
    'warnings.warn',
})
_MESAJ_ANAHTARLARI = frozenset({'reason', 'msg', 'message'})


@dataclass(frozen=True)
class Ihlal:
    satir: int
    sutun: int
    bitis_satir: int
    bitis_sutun: int
    ifade: str


@dataclass
class Sonuc:
    ihlaller: List[Ihlal] = field(default_factory=list)
    #: (satır, statik docs-göreli yol) — tohumların çözülebilen kısmı.
    tohumlar: List[tuple] = field(default_factory=list)
    #: ``kanit_gerekli(...)`` / ``kanit_cikti(...)`` çağrı satırları.
    kapi_cagrilari: List[int] = field(default_factory=list)
    #: Modül düzeyinde kirli kalan adlar — başka test modülü bunları ithal
    #: ederse orada da kirlidir (``tara_agac`` iki geçişte çözer).
    disa_acik: Set[str] = field(default_factory=set)


def _nokta_adi(dugum) -> Optional[str]:
    if isinstance(dugum, ast.Name):
        return dugum.id
    if isinstance(dugum, ast.Attribute):
        taban = _nokta_adi(dugum.value)
        return None if taban is None else taban + '.' + dugum.attr
    return None


def _cagri_adi(dugum) -> Optional[str]:
    return _nokta_adi(dugum.func) if isinstance(dugum, ast.Call) else None


def _kapi_mi(dugum) -> bool:
    ad = _cagri_adi(dugum)
    return ad is not None and ad.split('.')[-1] in KAPILAR


def _cozucu_mu(dugum) -> bool:
    ad = _cagri_adi(dugum)
    return ad is not None and ad.split('.')[-1] == COZUCU


def _parametrize_mi(dugum) -> bool:
    ad = _cagri_adi(dugum)
    return ad is not None and ad.endswith('mark.parametrize')


def _duzlestir(dugum) -> list:
    """Yol ifadesinin parçaları (sabitler dize, gerisi None)."""
    if isinstance(dugum, ast.BinOp) and isinstance(dugum.op, ast.Div):
        return _duzlestir(dugum.left) + _duzlestir(dugum.right)
    if isinstance(dugum, ast.Call) and (_cagri_adi(dugum) in _YAYAN_CAGRILAR
                                        or _cozucu_mu(dugum)):
        parca = []
        for a in dugum.args:
            parca += _duzlestir(a)
        return parca
    if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str):
        return [p for p in re.split(r'[/\\]', dugum.value) if p != ''] or ['']
    return [None]


def _statik_yol(parcalar: list) -> Optional[str]:
    for i in range(len(parcalar) - 1):
        if parcalar[i] == 'docs' and parcalar[i + 1] in _ALT:
            yol = []
            for p in parcalar[i:]:
                if p is None:
                    break
                yol.append(p)
            return '/'.join(yol)
    return None


class _Tarayici:
    def __init__(self, kaynak: str, disa_acik=None):
        self.kaynak = kaynak
        #: başka test modüllerinin dışa açık kirli adları: modül adı -> adlar
        self.disa_acik: Dict[str, Set[str]] = disa_acik or {}
        #: bu modülde bir test modülüne verilen takma ad -> modül adı
        self.modul_takma: Dict[str, str] = {}
        self.agac = ast.parse(kaynak)
        self.ebeveyn: Dict[int, ast.AST] = {}
        for d in ast.walk(self.agac):
            for c in ast.iter_child_nodes(d):
                self.ebeveyn[id(c)] = d
        self.dizeler_haric: Set[int] = set()
        self.mesaj: Set[int] = set()
        self.tohum: Set[int] = set()
        self.sinif_kirli: Set[str] = set()
        #: modül/sınıf düzeyi ``AD = <ifade>`` atamaları (parametrize çözümü)
        self.sabitler: Dict[str, ast.AST] = {}
        for d in ast.walk(self.agac):
            if isinstance(d, (ast.Module, ast.ClassDef)):
                for s in d.body:
                    if (isinstance(s, ast.Assign) and len(s.targets) == 1
                            and isinstance(s.targets[0], ast.Name)):
                        self.sabitler[s.targets[0].id] = s.value
        self.sinif_adlari = {d.name for d in ast.walk(self.agac)
                             if isinstance(d, ast.ClassDef)}
        self.sonuc = Sonuc()
        self._hazirla()

    # -- hazırlık ---------------------------------------------------------
    def _hazirla(self):
        for d in ast.walk(self.agac):
            govde = getattr(d, 'body', None)
            if isinstance(govde, list):
                for s in govde:
                    if (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                            and isinstance(s.value.value, str)):
                        self.dizeler_haric.add(id(s.value))
            if isinstance(d, ast.Assert) and d.msg is not None:
                self._isaretle(d.msg, self.mesaj)
            if isinstance(d, ast.Raise):
                for alt in (d.exc, d.cause):
                    if alt is not None:
                        self._isaretle(alt, self.mesaj)
            if isinstance(d, ast.Call):
                if _cagri_adi(d) in _MESAJ_CAGRILARI:
                    for a in d.args:
                        self._isaretle(a, self.mesaj)
                for k in d.keywords:
                    if k.arg in _MESAJ_ANAHTARLARI:
                        self._isaretle(k.value, self.mesaj)
                if _kapi_mi(d):
                    self.sonuc.kapi_cagrilari.append(d.lineno)
        for d in ast.walk(self.agac):
            if id(d) in self.mesaj or id(d) in self.dizeler_haric:
                continue
            if (isinstance(d, ast.Constant) and isinstance(d.value, str)
                    and _DIZE.search(d.value)):
                self.tohum.add(id(d))
            elif _cozucu_mu(d):
                self.tohum.add(id(d))
            elif isinstance(d, (ast.Call, ast.BinOp)):
                p = _duzlestir(d)
                if isinstance(d, ast.BinOp):
                    # yalnız 'docs' / 'scofield' birleşiminin EN KÜÇÜK düğümü
                    sag = _duzlestir(d.right)
                    sol = _duzlestir(d.left)
                    if sag[:1] and sag[0] in _ALT and sol[-1:] == ['docs']:
                        self.tohum.add(id(d))
                elif _statik_yol(p) is not None and _cagri_adi(d) in _YAYAN_CAGRILAR:
                    self.tohum.add(id(d))
        for d in ast.walk(self.agac):
            if id(d) in self.tohum:
                ust = d
                while True:
                    e = self.ebeveyn.get(id(ust))
                    if e is None or not self._yol_zinciri(e, ust):
                        break
                    ust = e
                yol = _statik_yol(_duzlestir(ust))
                if yol is None and isinstance(d, ast.Constant):
                    m = _DIZE.search(d.value)
                    yol = d.value[m.start():].lstrip('/\\') if m else None
                if yol is not None:
                    self.sonuc.tohumlar.append((d.lineno, yol))

    def _isaretle(self, dugum, kume):
        for d in ast.walk(dugum):
            kume.add(id(d))

    @staticmethod
    def _yol_zinciri(ebeveyn, cocuk) -> bool:
        if isinstance(ebeveyn, ast.BinOp) and isinstance(ebeveyn.op, ast.Div):
            return True
        return (isinstance(ebeveyn, ast.Call) and cocuk in ebeveyn.args
                and _cagri_adi(ebeveyn) in _YAYAN_CAGRILAR)

    # -- kirlilik ------------------------------------------------------------
    def kirli(self, d, durum) -> bool:
        if d is None:
            return False
        if id(d) in self.tohum:
            return True
        if isinstance(d, ast.Call):
            if _kapi_mi(d):
                return False
            ad = _cagri_adi(d)
            if ad in _YAYAN_CAGRILAR:
                return any(self.kirli(a, durum) for a in d.args)
            if (isinstance(d.func, ast.Attribute) and d.func.attr in _YAYAN_YONTEMLER):
                return self.kirli(d.func.value, durum)
            return False
        if isinstance(d, ast.Name):
            return durum.get(d.id, False)
        if isinstance(d, ast.Attribute):
            if d.attr in _YAYAN_NITELIKLER:
                return self.kirli(d.value, durum)
            taban = d.value
            if (isinstance(taban, ast.Name)
                    and (taban.id in ('self', 'cls') or taban.id in self.sinif_adlari)
                    and d.attr in self.sinif_kirli):
                return True
            if (isinstance(taban, ast.Name) and taban.id in self.modul_takma
                    and d.attr in self.disa_acik.get(self.modul_takma[taban.id], ())):
                return True                  # ikiz.CANLI_TUR_RAPORU
            return False
        if isinstance(d, ast.BinOp):
            return self.kirli(d.left, durum) or self.kirli(d.right, durum)
        if isinstance(d, ast.JoinedStr):
            return any(self.kirli(v, durum) for v in d.values)
        if isinstance(d, ast.FormattedValue):
            return self.kirli(d.value, durum)
        if isinstance(d, (ast.Tuple, ast.List, ast.Set)):
            return any(self.kirli(e, durum) for e in d.elts)
        if isinstance(d, ast.Dict):
            return any(self.kirli(v, durum) for v in d.values)
        if isinstance(d, ast.IfExp):
            return self.kirli(d.body, durum) or self.kirli(d.orelse, durum)
        if isinstance(d, ast.BoolOp):
            return any(self.kirli(v, durum) for v in d.values)
        if isinstance(d, (ast.Subscript, ast.Starred, ast.NamedExpr)):
            return self.kirli(d.value, durum)
        return False

    def _tasiyor(self, ebeveyn, cocuk, durum) -> bool:
        """``ebeveyn`` kirliliği ``cocuk``'tan devralıyor mu (yol hâlâ akıyor mu)?"""
        if isinstance(ebeveyn, (ast.BinOp, ast.JoinedStr, ast.FormattedValue,
                                ast.Tuple, ast.List, ast.Set, ast.IfExp,
                                ast.BoolOp, ast.Starred, ast.NamedExpr)):
            return self.kirli(ebeveyn, durum)
        if isinstance(ebeveyn, ast.Dict):
            return cocuk in ebeveyn.values and self.kirli(ebeveyn, durum)
        if isinstance(ebeveyn, ast.Subscript):
            return cocuk is ebeveyn.value
        if isinstance(ebeveyn, ast.Call):
            if _kapi_mi(ebeveyn):
                return False
            if cocuk in ebeveyn.args and _cagri_adi(ebeveyn) in _YAYAN_CAGRILAR:
                return True
            if (cocuk is ebeveyn.func and isinstance(cocuk, ast.Attribute)
                    and cocuk.attr in _YAYAN_YONTEMLER):
                return True
            return False
        if isinstance(ebeveyn, ast.Attribute):
            return ebeveyn.attr in _YAYAN_NITELIKLER or (
                ebeveyn.attr in _YAYAN_YONTEMLER
                and isinstance(self.ebeveyn.get(id(ebeveyn)), ast.Call))
        return False

    def _zararsiz(self, ebeveyn, cocuk) -> bool:
        if isinstance(ebeveyn, ast.Call) and _kapi_mi(ebeveyn):
            return True                      # kapıdan geçti
        if isinstance(ebeveyn, ast.arguments):
            return True                      # varsayılan değer -> parametre
        if (isinstance(ebeveyn, ast.Call) and _parametrize_mi(ebeveyn)
                and (cocuk in ebeveyn.args or any(cocuk is k.value
                                                  for k in ebeveyn.keywords))):
            return True                      # değer -> test parametresi
        if isinstance(ebeveyn, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            return cocuk is ebeveyn.value
        if isinstance(ebeveyn, (ast.For, ast.AsyncFor, ast.comprehension)):
            return cocuk is ebeveyn.iter
        if isinstance(ebeveyn, ast.Compare):
            return True
        if isinstance(ebeveyn, ast.Attribute):
            if ebeveyn.attr in _AD_NITELIKLERI:
                return True
            if ebeveyn.attr in _KARSILASTIRMA_YONTEMLERI:
                return True
        if isinstance(ebeveyn, ast.Call) and cocuk in ebeveyn.args:
            f = ebeveyn.func
            if isinstance(f, ast.Attribute) and f.attr in _KARSILASTIRMA_YONTEMLERI:
                return True
        if isinstance(ebeveyn, (ast.If, ast.While, ast.IfExp)):
            return cocuk is ebeveyn.test
        if isinstance(ebeveyn, (ast.Expr, ast.UnaryOp)):
            return True
        return False

    def _parametre_kirleri(self, fonk, durum) -> Dict[str, bool]:
        """``@pytest.mark.parametrize`` ile gelen parametrelerin konum konum kirliliği."""
        sonuc: Dict[str, bool] = {}
        for dek in fonk.decorator_list:
            if not (isinstance(dek, ast.Call) and _parametrize_mi(dek) and dek.args):
                continue
            adlar_d = dek.args[0]
            if isinstance(adlar_d, ast.Constant) and isinstance(adlar_d.value, str):
                adlar = [a.strip() for a in adlar_d.value.split(',') if a.strip()]
            elif isinstance(adlar_d, (ast.Tuple, ast.List)):
                adlar = [e.value for e in adlar_d.elts if isinstance(e, ast.Constant)]
            else:
                continue
            degerler = dek.args[1] if len(dek.args) > 1 else next(
                (k.value for k in dek.keywords if k.arg == 'argvalues'), None)
            cozulen = degerler
            if isinstance(cozulen, ast.Name) and cozulen.id in self.sabitler:
                cozulen = self.sabitler[cozulen.id]
            elif (isinstance(cozulen, ast.Attribute) and isinstance(cozulen.value, ast.Name)
                    and cozulen.attr in self.sabitler):
                cozulen = self.sabitler[cozulen.attr]
            if isinstance(cozulen, (ast.Tuple, ast.List)):
                for ad in adlar:
                    sonuc.setdefault(ad, False)
                for satir in cozulen.elts:
                    if isinstance(satir, ast.Call) and _cagri_adi(satir) in (
                            'pytest.param', 'param'):
                        ogeler = satir.args
                    elif len(adlar) > 1 and isinstance(satir, (ast.Tuple, ast.List)):
                        ogeler = satir.elts
                    else:
                        ogeler = [satir]
                    for ad, oge in zip(adlar, ogeler):
                        if self.kirli(oge, durum):
                            sonuc[ad] = True
            else:
                kir = self.kirli(degerler, durum)
                for ad in adlar:
                    sonuc[ad] = sonuc.get(ad, False) or kir
        return sonuc

    def _ihlal(self, d):
        seg = ast.get_source_segment(self.kaynak, d) or type(d).__name__
        self.sonuc.ihlaller.append(Ihlal(d.lineno, d.col_offset, d.end_lineno,
                                         d.end_col_offset, ' '.join(seg.split())[:160]))

    def _cukur(self, d, durum):
        """Kirli ``d`` bir çukurda: kap ise öğelerine in, değilse ihlal yaz."""
        if isinstance(d, (ast.Tuple, ast.List, ast.Set)):
            for e in d.elts:
                if self.kirli(e, durum):
                    self._cukur(e, durum)
            return
        if isinstance(d, ast.Dict):
            for v in d.values:
                if self.kirli(v, durum):
                    self._cukur(v, durum)
            return
        if isinstance(d, ast.Starred):
            self._cukur(d.value, durum)
            return
        self._ihlal(d)

    # -- ifade gezgini -------------------------------------------------------
    def ifade(self, d, durum):
        """``d`` ağacındaki çukura akan maksimal kirli düğümleri bul."""
        if d is None or id(d) in self.mesaj:
            return
        if isinstance(d, ast.Lambda):
            self.ifade(d.body, dict(durum))
            return
        if isinstance(d, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            ic = dict(durum)
            for g in d.generators:
                self.ifade(g.iter, ic)
                kir = self.kirli(g.iter, ic)
                for n in ast.walk(g.target):
                    if isinstance(n, ast.Name):
                        ic[n.id] = kir
                for k in g.ifs:
                    self.ifade(k, ic)
            if isinstance(d, ast.DictComp):
                self.ifade(d.key, ic)
                self.ifade(d.value, ic)
            else:
                self.ifade(d.elt, ic)
            return
        if self.kirli(d, durum):
            e = self.ebeveyn.get(id(d))
            if e is not None and self._tasiyor(e, d, durum):
                pass  # karar ebeveynde verilir
            elif e is None or self._zararsiz(e, d):
                pass
            else:
                self._cukur(d, durum)
        for c in ast.iter_child_nodes(d):
            if isinstance(c, (ast.expr, ast.comprehension, ast.keyword, ast.arg,
                              ast.arguments)):
                if isinstance(c, ast.comprehension):
                    continue
                self.ifade(c, durum)

    # -- deyim gezgini -------------------------------------------------------
    def _hedef(self, hedef, kir, durum, sinif):
        if isinstance(hedef, ast.Name):
            durum[hedef.id] = kir
            if sinif and kir:
                self.sinif_kirli.add(hedef.id)
        elif isinstance(hedef, (ast.Tuple, ast.List)):
            for e in hedef.elts:
                self._hedef(e, kir, durum, sinif)
        elif isinstance(hedef, ast.Attribute):
            if (kir and isinstance(hedef.value, ast.Name)
                    and hedef.value.id in ('self', 'cls')):
                self.sinif_kirli.add(hedef.attr)
        elif isinstance(hedef, ast.Starred):
            self._hedef(hedef.value, kir, durum, sinif)

    def govde(self, deyimler, durum, sinif=False, ertelenen=None):
        kapi_goruldu = False
        for s in deyimler:
            if isinstance(s, (ast.Import, ast.ImportFrom)):
                self._ithal(s, durum, kapi_goruldu)
            self.deyim(s, durum, sinif, ertelenen)
            if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kapi_goruldu = kapi_goruldu or any(
                    isinstance(n, ast.Call) and _kapi_mi(n) for n in ast.walk(s))

    def _ithal(self, s, durum, kapi_goruldu):
        """İthal deyimi: kanıt modülü ithali ve test modülleri arası kirlilik.

        Kanıt dizinindeki bir modülün ithali (``from docs.scofield.betikler
        import izolasyon``) bir OKUMADIR; aynı gövdede ÖNCESİNDE bir kapı
        çağrısı yoksa ihlaldir.
        """
        if isinstance(s, ast.Import):
            for a in s.names:
                if _MODUL.match(a.name) and not kapi_goruldu:
                    self._ihlal(s)
                if a.name in self.disa_acik:
                    self.modul_takma[a.asname or a.name] = a.name
            return
        modul = s.module or ''
        if s.level == 0 and _MODUL.match(modul) and not kapi_goruldu:
            self._ihlal(s)
        for a in s.names:
            ad = a.asname or a.name
            tam = modul + '.' + a.name
            if s.level == 0 and _MODUL.match(tam) and not kapi_goruldu:
                self._ihlal(s)
            if tam in self.disa_acik:
                self.modul_takma[ad] = tam
            elif a.name in self.disa_acik.get(modul, ()):
                durum[ad] = True

    def deyim(self, s, durum, sinif, ertelenen):
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dek in s.decorator_list:
                self.ifade(dek, durum)
            for v in s.args.defaults + [k for k in s.args.kw_defaults if k]:
                self.ifade(v, durum)
            # Sınıf gövdesindeki yöntem, sınıf adlarını çıplak ad olarak
            # GÖRMEZ (Python kapsam kuralı): modül durumuyla gezilir.
            ertelenen.append((s, None if sinif else durum))
            durum[s.name] = False
            return
        if isinstance(s, ast.ClassDef):
            for dek in s.decorator_list:
                self.ifade(dek, durum)
            ic = dict(durum)
            self.govde(s.body, ic, sinif=True, ertelenen=ertelenen)
            return
        if isinstance(s, ast.Assign):
            self.ifade(s.value, durum)
            kir = self.kirli(s.value, durum)
            for t in s.targets:
                self._hedef(t, kir, durum, sinif)
            return
        if isinstance(s, ast.AnnAssign):
            self.ifade(s.value, durum)
            self._hedef(s.target, self.kirli(s.value, durum), durum, sinif)
            return
        if isinstance(s, ast.AugAssign):
            self.ifade(s.value, durum)
            if isinstance(s.target, ast.Name):
                durum[s.target.id] = durum.get(s.target.id, False) or self.kirli(s.value, durum)
            return
        if isinstance(s, (ast.For, ast.AsyncFor)):
            self.ifade(s.iter, durum)
            self._hedef(s.target, self.kirli(s.iter, durum), durum, sinif)
            self.govde(s.body, durum, sinif, ertelenen)
            self.govde(s.orelse, durum, sinif, ertelenen)
            return
        if isinstance(s, (ast.With, ast.AsyncWith)):
            for w in s.items:
                self.ifade(w.context_expr, durum)
                if w.optional_vars is not None:
                    self._hedef(w.optional_vars, False, durum, sinif)
            self.govde(s.body, durum, sinif, ertelenen)
            return
        if isinstance(s, (ast.If, ast.While)):
            self.ifade(s.test, durum)
            self.govde(s.body, durum, sinif, ertelenen)
            self.govde(s.orelse, durum, sinif, ertelenen)
            return
        if isinstance(s, ast.Try) or type(s).__name__ == 'TryStar':
            self.govde(s.body, durum, sinif, ertelenen)
            for h in s.handlers:
                self.govde(h.body, durum, sinif, ertelenen)
            self.govde(s.orelse, durum, sinif, ertelenen)
            self.govde(s.finalbody, durum, sinif, ertelenen)
            return
        if isinstance(s, ast.Match):
            self.ifade(s.subject, durum)
            for c in s.cases:
                self.govde(c.body, durum, sinif, ertelenen)
            return
        for c in ast.iter_child_nodes(s):
            if isinstance(c, ast.expr):
                self.ifade(c, durum)

    def calistir(self) -> Sonuc:
        ertelenen: list = []
        modul: Dict[str, bool] = {}
        self.govde(self.agac.body, modul, ertelenen=ertelenen)
        self.sonuc.disa_acik = {ad for ad, kir in modul.items() if kir}
        while ertelenen:
            fonk, dis = ertelenen.pop(0)
            dis = modul if dis is None else dis
            ic = dict(dis)
            ic.update({k: v for k, v in modul.items() if k not in ic})
            argumanlar = fonk.args
            varsayilanlar = argumanlar.defaults
            konumsal = argumanlar.posonlyargs + argumanlar.args
            for a, v in zip(konumsal[len(konumsal) - len(varsayilanlar):], varsayilanlar):
                ic[a.arg] = self.kirli(v, dis)
            for a in konumsal[:len(konumsal) - len(varsayilanlar)] + argumanlar.kwonlyargs:
                ic[a.arg] = False
            ic.update(self._parametre_kirleri(fonk, dis))
            self.govde(fonk.body, ic, ertelenen=ertelenen)
        self.sonuc.ihlaller = sorted(set(self.sonuc.ihlaller),
                                     key=lambda i: (i.satir, i.sutun))
        self.sonuc.tohumlar = sorted(set(self.sonuc.tohumlar))
        return self.sonuc


def tara(kaynak: str, disa_acik=None) -> Sonuc:
    """``kaynak`` Python metnini tarar; ihlaller, tohumlar ve kapı çağrıları.

    ``disa_acik``: başka test modüllerinin dışa açık kirli adları
    (modül adı -> ad kümesi); tek dosya taramasında boş bırakılabilir.
    """
    return _Tarayici(kaynak, disa_acik).calistir()


def modul_adi(bagil: str) -> str:
    """``tests/support/x.py`` -> ``tests.support.x``."""
    ad = bagil[:-3] if bagil.endswith('.py') else bagil
    ad = ad.replace('/', '.')
    return ad[:-len('.__init__')] if ad.endswith('.__init__') else ad


def tara_agac(kaynaklar: Dict[str, str], tur_siniri: int = 5) -> Dict[str, Sonuc]:
    """Bir test ağacını (depo-göreli yol -> kaynak) modüller arası kirlilikle tarar.

    Bir modülün modül düzeyinde kirli adı (ör. ``sahte_sayfa.CANLI_TUR_RAPORU``)
    onu ithal eden modülde de kirlidir. Dışa açık kümeler sabitlenene kadar
    (en çok ``tur_siniri`` tur) yinelenir.
    """
    disa_acik: Dict[str, Set[str]] = {}
    sonuc: Dict[str, Sonuc] = {b: tara(k) for b, k in kaynaklar.items()}
    for _ in range(tur_siniri):
        yeni = {modul_adi(b): s.disa_acik for b, s in sonuc.items() if s.disa_acik}
        if yeni == disa_acik:
            break
        disa_acik = yeni
        # Yalnız dışa açık kirli adı olan bir modülü ANAN dosyalar yeniden
        # taranır (metin süzgeci; ithal eden dosya modülün son adını taşır).
        kisa = {m.rsplit('.', 1)[-1] for m in disa_acik}
        for b, k in kaynaklar.items():
            if any(ad in k for ad in kisa):
                sonuc[b] = tara(k, disa_acik)
    return sonuc
