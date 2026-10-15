# -*- coding: utf-8 -*-
"""ÖH D28 / ihracat a1 — OH-D27-11 (ihracat payı) bekçileri.

Kalem: "input_guard merkezine bağlı olmayan bağımsız çevirici tanımları".
D27 raporu §4 ihracat için 8 tanım saymıştı; ölçüldü ki sahada 19 el yazısı
kapı vardı ve ürün yolundaki asıl kapı listede YOKTU.

Bu dosya üç şeyi bekler:

1. **Bağ gerçek olsun** — çevirici merkezdeki NESNEYİ çağırsın (kimlik
   ölçüsü). ``_input_guards``in künyesindeki dersin aynısı: kopya gövdeler
   ``inspect.getsource`` ile birebir görünür ama ``is`` özdeşliği yalan
   söylemez.
2. **Sözleşme tek olsun** — aynı girdi, aynı karar; ``bool`` hiçbir yerde
   ölçü sayılmasın (``float(True) == 1.0``).
3. **Ürün fail-closed olsun** — çözülemeyen alan "eksik" diye raporlansın,
   uydurma sayı yayımlanmasın (Doktrin 1).
"""

import numpy as np
import pytest

from hrma.utils import input_guard as ig

from hrma.export.cad_export import _as_float, normalize_anti_vortex_mm
from hrma.export.drawing_generator import _num as dg_num
from hrma.export.motor_geometry import (
    _first_positive, _num as mg_num, _real_mm,
    length_in_meters, length_in_meters_banded,
    normalise_export_geometry, resolve_length_m,
)
from hrma.export.step_export import (
    _first_positive_local, _num as se_num,
)
from hrma.export.openrocket_integration import (
    OpenRocketExporter, _finite_number, _finite_positive,
)
from hrma.export.cad_visualization import _real_nested, _real_scalar


# D27 raporu §4'ün ihracat için saydığı SEKİZ tanım — kalemin adlı kapsamı.
D27_SEKIZ_TANIM = {
    'export/cad_export.py:_as_float': (_as_float, 'finite_number'),
    'export/drawing_generator.py:_num': (dg_num, 'finite_number'),
    'export/motor_geometry.py:_num': (mg_num, 'finite_number'),
    'export/motor_geometry.py:_first_positive': (
        _first_positive, 'first_finite_positive'),
    'export/step_export.py:_num': (se_num, 'finite_number'),
    'export/step_export.py:_first_positive_local': (
        _first_positive_local, 'first_finite_positive'),
    'export/openrocket_integration.py:_finite_positive': (
        _finite_positive, 'finite_positive'),
    'export/openrocket_integration.py:_finite_number': (
        _finite_number, 'finite_number'),
}

# Onarımın ölçüm sırasında ORTAYA ÇIKARDIĞI, D27 listesinde OLMAYAN kapılar.
# Ürün yolundaki asıl kapı bunların içindedir (``resolve_length_m``).
LISTEDE_OLMAYAN_KAPILAR = {
    'export/motor_geometry.py:_real_mm': (_real_mm, 'first_finite_positive'),
    'export/motor_geometry.py:length_in_meters': (
        length_in_meters, 'finite_positive'),
    'export/motor_geometry.py:length_in_meters_banded': (
        length_in_meters_banded, 'finite_positive'),
    'export/motor_geometry.py:resolve_length_m': (
        resolve_length_m, 'finite_positive'),
    'export/cad_visualization.py:_real_scalar': (
        _real_scalar, 'finite_positive'),
    'export/cad_visualization.py:_real_nested': (
        _real_nested, 'finite_positive'),
}

TUM_KAPILAR = dict(D27_SEKIZ_TANIM, **LISTEDE_OLMAYAN_KAPILAR)


def _merkezi_cagiriyor(fn, merkez_adi):
    """Fonksiyon merkezdeki NESNEYİ mi çağırıyor? (kimlik ölçüsü)"""
    hedef = getattr(ig, merkez_adi)
    globaller = getattr(fn, '__globals__', {})
    adlar = set(getattr(fn, '__code__').co_names or ())
    return merkez_adi in adlar and globaller.get(merkez_adi) is hedef


class TestOHD2711MerkezeBaglilik:
    """Bağ metinle değil KİMLİKLE kurulur."""

    @pytest.mark.parametrize('kimlik', sorted(D27_SEKIZ_TANIM))
    def test_d27_sekiz_tanimi_merkezi_cagirir(self, kimlik):
        fn, merkez_adi = D27_SEKIZ_TANIM[kimlik]
        assert _merkezi_cagiriyor(fn, merkez_adi), (
            f'{kimlik} merkezî input_guard.{merkez_adi} nesnesini '
            f'ÇAĞIRMIYOR — kendi kopya kapısını yazmış olabilir.')

    @pytest.mark.parametrize('kimlik', sorted(LISTEDE_OLMAYAN_KAPILAR))
    def test_listede_olmayan_kapilar_da_merkezi_cagirir(self, kimlik):
        fn, merkez_adi = LISTEDE_OLMAYAN_KAPILAR[kimlik]
        assert _merkezi_cagiriyor(fn, merkez_adi), (
            f'{kimlik} merkezî input_guard.{merkez_adi} nesnesini '
            f'ÇAĞIRMIYOR.')


class TestOHD2711BoolOlcuDegildir:
    """``float(True) == 1.0`` — True bir çap, boy ya da kütle DEĞİLDİR."""

    #: (ad, çağrılabilir, yedek parametresi alır mı)
    CEVIRICILER = [
        ('cad_export._as_float', _as_float, False),
        ('drawing_generator._num', dg_num, True),
        ('motor_geometry._num', mg_num, True),
        ('motor_geometry._first_positive', _first_positive, False),
        ('step_export._num', se_num, True),
        ('step_export._first_positive_local', _first_positive_local, False),
        ('openrocket._finite_positive', _finite_positive, False),
        ('openrocket._finite_number', _finite_number, False),
        ('motor_geometry._real_mm', _real_mm, False),
        ('cad_visualization._real_scalar', _real_scalar, False),
    ]

    YEDEK = -98765.0

    @pytest.mark.parametrize('ad,fn,yedek_alir', CEVIRICILER,
                             ids=[c[0] for c in CEVIRICILER])
    @pytest.mark.parametrize('deger', [True, False],
                             ids=['True', 'False'])
    def test_python_bool_sayiya_cevrilmez(self, ad, fn, yedek_alir, deger):
        out = fn(deger, self.YEDEK) if yedek_alir else fn(deger)
        cozulemedi = (out == self.YEDEK) if yedek_alir else (out is None)
        assert cozulemedi, (
            f'{ad}({deger!r}) -> {out!r}: doğruluk değeri sayı sayıldı.')

    @pytest.mark.parametrize('ad,fn,yedek_alir', CEVIRICILER,
                             ids=[c[0] for c in CEVIRICILER])
    def test_numpy_bool_da_sayiya_cevrilmez(self, ad, fn, yedek_alir):
        """``np.bool_`` Python ``bool``un ALT SINIFI DEĞİLDİR.

        ``isinstance(np.bool_(True), bool)`` ``False`` verir ama ``float()``
        onu 1.0 yapar. Çözücü sonuçları numpy taşıdığı için bu delik
        gerçektir; merkez ``dtype.kind == 'b'`` ördek denetimiyle kapatır.
        """
        deger = np.bool_(True)
        out = fn(deger, self.YEDEK) if yedek_alir else fn(deger)
        cozulemedi = (out == self.YEDEK) if yedek_alir else (out is None)
        assert cozulemedi, (
            f'{ad}(np.bool_(True)) -> {out!r}: numpy doğruluk değeri sayı '
            f'sayıldı.')

    def test_uzunluk_cozucusu_bool_u_eksik_sayar(self):
        assert resolve_length_m(
            {'motor_geometry': {'chamber_length': True}},
            'chamber_length') == (None, 'missing')
        assert length_in_meters_banded(
            True, 'chamber_diameter', 1.0) == (None, 'missing')
        assert length_in_meters(True, 5.0) == (None, 'missing')


class TestOHD2711MesruSayilarGecer:
    """Kapatma MEŞRU girdiyi elemez — sözleşme daralmadı."""

    def test_sifir_ve_negatif_sonlu_sayidir(self):
        # 0 m/s rüzgâr "veri yok" DEĞİLDİR (openrocket künyesi).
        assert _finite_number(0) == 0.0
        assert _finite_number(-3.5) == -3.5
        assert mg_num(0, 1.0) == 0.0

    def test_sifir_ve_negatif_uzunluk_DEGILDIR(self):
        assert _finite_positive(0) is None
        assert _finite_positive(-3.5) is None
        assert _first_positive(0, -1, 7.0) == 7.0

    def test_numpy_skaleri_MESRU_sayidir(self):
        """Uç katmanının tip kısıtı değer katmanına TAŞINMADI.

        ``np.float32``/``np.int64`` ``(int, float, str)`` örneği DEĞİLDİR;
        kısıt taşınsaydı ihracat hattı çözücünün kendi sayılarını
        reddederdi.
        """
        assert not isinstance(np.float32(5.0), (int, float, str))
        assert _finite_positive(np.float32(5.0)) == pytest.approx(5.0)
        assert mg_num(np.int64(7), 1.0) == 7.0
        assert _as_float(np.float32(2.5)) == pytest.approx(2.5)

    def test_okunamayan_deger_yedege_duser(self):
        assert mg_num('abc', 4.0) == 4.0
        assert mg_num(float('nan'), 4.0) == 4.0
        assert _as_float(float('inf')) is None


class TestOHD2711UrunFailClosed:
    """Çözülemeyen alan uydurulmaz, ADIYLA eksik sayılır (Doktrin 1)."""

    def test_eng_kritik_alanlari_bool_u_eksik_raporlar(self):
        cozum = OpenRocketExporter().resolve_eng_inputs(
            {'motor_geometry': {'case_diameter': True,
                                'chamber_length': True}})
        eksikler = cozum.get('missing_fields') or []
        assert 'case_diameter' in eksikler, (
            'True bir gövde çapı sayıldı; .eng künyesine uydurma 1,0 m iner.')
        assert 'chamber_length' in eksikler
        assert cozum.get('case_diameter') is None
        assert cozum.get('chamber_length') is None

    def test_disa_aktarim_geometrisi_bool_u_cozmez(self):
        kopya, rapor = normalise_export_geometry({'chamber_diameter': True})
        assert rapor['fields'].get('chamber_diameter') in (None, 'missing')
        # Çözülemeyen alan DOKUNULMADAN kalır — uydurma metre yazılmaz.
        assert kopya['chamber_diameter'] is True

    def test_girdap_onleyici_birimi_cozulemez_kalir(self):
        av = normalize_anti_vortex_mm({'diameter': True, 'height': True},
                                      tank_diameter_mm=200.0)
        assert av['units'] == 'UNRESOLVED'


class TestOHD2711MerkezSozlesmesi:
    """Merkezin kendi kapıları — kural burada yaşıyor."""

    def test_finite_number_kurali(self):
        assert ig.finite_number(True) is None
        assert ig.finite_number(np.bool_(False)) is None
        assert ig.finite_number(0) == 0.0
        assert ig.finite_number(-1.5) == -1.5
        assert ig.finite_number(float('nan')) is None
        assert ig.finite_number('abc', 'YEDEK') == 'YEDEK'

    def test_finite_positive_kurali(self):
        assert ig.finite_positive(0) is None
        assert ig.finite_positive(-1) is None
        assert ig.finite_positive('2.5') == 2.5
        assert ig.finite_positive(True) is None

    def test_first_finite_positive_sirayi_korur(self):
        assert ig.first_finite_positive(None, 'abc', -2, 0, 9.0) == 9.0
        assert ig.first_finite_positive() is None
        assert ig.first_finite_positive(True, 4.0) == 4.0

    def test_disa_acilan_adlar_kunyede(self):
        for ad in ('finite_number', 'finite_positive', 'first_finite_positive'):
            assert ad in ig.__all__


class TestOHD2711ElYazisiKapiMandali:
    """Sahada kalan el yazısı kapılar — KÜME mandalı (sayı değil).

    D27 dersi 11: sayım mandalı yerine küme mandalı. Meşru bir kapı
    eklenirse bu küme ADIYLA güncellenir; sessizce büyümez.
    """

    #: Merkeze bağlanMAYAN kapılar. İkisi de saf değer kapısı DEĞİL, kendi
    #: ek anlamı olan çok adımlı ÇÖZÜCÜdür; ADIYLA sayılıyorlar.
    #:
    #: ÖH D31 / ihracat a1 (OH-D30-08 · P15B2-01 dağıtımı): kümeden
    #: ``cad_visualization.py:drawable_hole_count`` ÇIKARILDI — artık
    #: ``input_guard.finite_number`` merkezinden okuyor, yani mandalın
    #: aradığı anlamda "el yazısı" değil. Küme YALNIZ daraldı; bir kapı
    #: eklenmedi. (Sayı kapısı ile küme mandalı ayrımı: bu kümenin işi
    #: bağsız kalanları ADIYLA saymaktır, bağlananı listede tutmak
    #: mandalı kendi kendine yalanlatır.)
    BEKLENEN_BAGSIZ = {
        'hrma/export/openrocket_integration.py:resolve_average_thrust',
        'hrma/export/pdf_generator.py:resolve_chamber_pressure_bar',
    }

    def test_el_yazisi_kapi_kumesi_buyumedi(self):
        import ast
        import os

        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        saha = os.path.join(kok, 'hrma', 'export')
        merkez_adlar = {'finite_number', 'finite_positive',
                        'first_finite_positive', 'mm_to_m_read', 'num'}
        bulunan = set()

        for dizin, _alt, dosyalar in os.walk(saha):
            for ad in dosyalar:
                if not ad.endswith('.py'):
                    continue
                yol = os.path.join(dizin, ad)
                rel = os.path.relpath(yol, kok)
                agac = ast.parse(open(yol, encoding='utf-8').read())
                for dugum in ast.walk(agac):
                    if not isinstance(dugum, ast.FunctionDef):
                        continue
                    govde = ast.dump(dugum)
                    cagrilan = {
                        n.func.id for n in ast.walk(dugum)
                        if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Name)}
                    if 'float' not in cagrilan:
                        continue
                    if not (('isfinite' in govde) or ("'inf'" in govde)
                            or ('Inf' in govde)):
                        continue
                    arg_sayisi = (len(dugum.args.args)
                                  + len(dugum.args.posonlyargs)
                                  + len(dugum.args.kwonlyargs)
                                  + (1 if dugum.args.vararg else 0))
                    boy = getattr(dugum, 'end_lineno',
                                  dugum.lineno) - dugum.lineno
                    if arg_sayisi > 3 or boy > 30:
                        continue
                    if cagrilan & merkez_adlar:
                        continue
                    bulunan.add('%s:%s' % (rel, dugum.name))

        yeni = bulunan - self.BEKLENEN_BAGSIZ
        assert not yeni, (
            'Merkeze bağlı OLMAYAN yeni el yazısı çevirici kapısı: '
            f'{sorted(yeni)}. Kapı merkezden çağrılmalı '
            '(input_guard.finite_number / finite_positive / '
            'first_finite_positive) ya da bu küme gerekçesiyle '
            'güncellenmeli.')
