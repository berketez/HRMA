# -*- coding: utf-8 -*-
"""ÖH Dalga-29 · kulvar **ihracat** · aşama 1 — onarım bekçileri.

Kalem: **OH-D28-07** (defter P15B4-12) — ``performance_summary``
sözlüğünde ``mass_breakdown`` adı kütle vaat ederken uzunluk (mm) ve
yoğunluk (kg/m3) da taşıyordu.

ÖLÇÜM (``docs/scofield/raw/OH/D29/ihracat/a1/``):

* ``once_p15b412.json`` (taban ``4dc63c11``) — 18 alanın 9'u sayısal;
  4'ü kütle (kg), **5'i değil**: 3 uzunluk (mm) + 2 yoğunluk (kg/m3).
* ``sonra_p15b412.json`` — 8 alanın 4'ü sayısal, **hepsi kütle**;
  kütle olmayan sayısal alan **0**.
* ``once_yerlesim.json`` / ``sonra_yerlesim.json`` (ÜRÜN KOŞTURULARAK,
  P09'un üç gerçek motor yanıtıyla) — **33 taşıma, 0 kayıp,
  0 değer değişimi**. Alanlar silinmedi; künyeleriyle birlikte
  ``geometry_summary`` (mm) ve yeni ``material_summary`` (kg/m3 +
  malzeme adı) sözlüklerine taşındı.

ÖK-05: bekçiler TERS-MUTASYONLA sınandı — onarım geçici olarak geri
alınır, bekçi KIRMIZI olur, bayt ``finally`` içinde geri yazılır
(kanıt: ``mutasyon.json``).
"""
import contextlib
import io
import json
import math
import os
import re
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

P09 = os.path.join(KOK, 'docs', 'scofield', 'raw', 'P09', 'cikti')

pytestmark = pytest.mark.skipif(
    not os.path.isdir(kanit_gerekli(P09)),
    reason=f'P09 fikstür dizini yok: {P09} (gerekçe DOĞRULANDI: os.path.isdir)')

#: Kütle dökümünden kendi boyut sözlüğüne taşınan alanlar (ölçülen 5
#: sayısal alan + onların künyeleri + birlikte taşınan malzeme adı).
TASINAN = {
    'geometry_summary': (
        'wall_thickness_mm', 'wall_thickness_source',
        'wall_thickness_recommended_mm', 'wall_thickness_note',
        'nozzle_wall_thickness_mm', 'nozzle_wall_thickness_source',
    ),
    'material_summary': (
        'chamber_material', 'chamber_mass_density_kg_m3',
        'chamber_mass_density_source', 'nozzle_mass_density_kg_m3',
        'nozzle_mass_density_source',
    ),
}

#: Metin (künye) alanı son ekleri — ``olcum_p15b412.py`` ile AYNI sözleşme.
METIN_SONEKLERI = ('_source', '_note', '_basis', '_scope', '_material',
                   '_reason', '_status', '_units')

_ONBELLEK = {}


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _fixture(ad):
    with open(kanit_gerekli(os.path.join(P09, f'motor_{ad}.json')), encoding='utf-8') as fh:
        return json.load(fh)


def _ozet(ad):
    """P09 motorunun ``performance_summary``i (modül ömrü boyunca tek koşum)."""
    if ad not in _ONBELLEK:
        from hrma.export.cad_visualization import MotorCADDesigner
        _ONBELLEK[ad] = _sessiz(
            MotorCADDesigner()._generate_cad_performance_summary,
            dict(_fixture(ad)))
    return _ONBELLEK[ad]


def _yollar(agac, hedef, onek=''):
    """``hedef`` adlı yaprağın bulunduğu TÜM yollar (kopya avı)."""
    bulunan = []
    for anahtar, deger in agac.items():
        yol = f'{onek}{anahtar}'
        if anahtar == hedef:
            bulunan.append(yol)
        if isinstance(deger, dict):
            bulunan.extend(_yollar(deger, hedef, yol + '.'))
    return bulunan


# ÖH D30 / fix-29b: bu üçlü motor türü sözlüğünün İKİZİydi (D29 ihracat
# a1, 737c5f77) ve ``test_sabit_tek_kaynak::test_motor_types_tek_tanim_
# noktasi`` bekçisini kırmızıya çevirdi. Muafiyet listesine eklenmedi —
# anonim af yok; fikstür tek kaynaktan OKUNUR, yarın dördüncü bir motor
# türü doğarsa bu dosya kendiliğinden onu da parametreler.
from hrma.constants import MOTOR_TYPES  # noqa: E402

P09_FIKSTURLERI = MOTOR_TYPES


class TestP15B412KutleDokumuYalnizKutle:
    """``mass_breakdown`` yayımlanan gövdede yalnız kütle taşır.

    Bu bekçi AST'ye değil ÜRÜNÜN KOŞUMUNA bakar: kaynakta alanı silip
    başka bir kod yolundan geri eklemek de yakalanır.
    """

    @pytest.mark.parametrize('ad', P09_FIKSTURLERI)
    def test_sayisal_alanlarin_hepsi_kutle(self, ad):
        mb = _ozet(ad)['mass_breakdown']
        disi = []
        for anahtar, deger in mb.items():
            if anahtar.endswith(METIN_SONEKLERI):
                continue          # künye metni
            if not isinstance(deger, (int, float)) or isinstance(deger, bool):
                if deger is not None:
                    disi.append((anahtar, type(deger).__name__))
                continue
            if not (anahtar.endswith('_mass') or anahtar == 'total_dry_mass'):
                disi.append((anahtar, deger))
        assert disi == [], (
            f'{ad}: kütle dökümünde kütle OLMAYAN sayısal alan: {disi}')

    @pytest.mark.parametrize('ad', P09_FIKSTURLERI)
    def test_mm_ve_yogunluk_soneki_KALMADI(self, ad):
        mb = _ozet(ad)['mass_breakdown']
        kirli = [k for k in mb
                 if k.endswith('_mm') or k.endswith('_kg_m3')]
        assert kirli == [], f'{ad}: {kirli}'

    @pytest.mark.parametrize('ad', P09_FIKSTURLERI)
    def test_kutleler_YERINDE(self, ad):
        """Onarım taşımadır, budama değil: dört kütle yerinde ve sayı."""
        mb = _ozet(ad)['mass_breakdown']
        for alan in ('chamber_mass', 'nozzle_mass', 'injector_mass',
                     'total_dry_mass'):
            assert isinstance(mb[alan], (int, float)), (ad, alan, mb[alan])
        assert mb['total_dry_mass'] == pytest.approx(
            mb['chamber_mass'] + mb['nozzle_mass'] + mb['injector_mass'],
            rel=1e-12)


class TestP15B412TasimaKayipDegil:
    """On bir alan YENİ adresinde, TEK kopya hâlinde duruyor."""

    @pytest.mark.parametrize('ad', P09_FIKSTURLERI)
    def test_yeni_adresinde_hepsi_var(self, ad):
        ozet = _ozet(ad)
        for sozluk, alanlar in TASINAN.items():
            assert sozluk in ozet, f'{ad}: {sozluk} sözlüğü yok'
            eksik = [a for a in alanlar if a not in ozet[sozluk]]
            assert eksik == [], f'{ad}: {sozluk} içinde eksik {eksik}'

    @pytest.mark.parametrize('ad', P09_FIKSTURLERI)
    def test_TEK_kopya_kaldi(self, ad):
        """Taşıma kopyalama değildir (TEK KAYNAK): her alan tam 1 yolda."""
        ozet = _ozet(ad)
        coklu = {}
        for sozluk, alanlar in TASINAN.items():
            for alan in alanlar:
                yerler = _yollar(ozet, alan)
                if yerler != [f'{sozluk}.{alan}']:
                    coklu[alan] = yerler
        assert coklu == {}, f'{ad}: alan birden fazla yolda / yanlış yolda: {coklu}'

    @pytest.mark.parametrize('ad', P09_FIKSTURLERI)
    def test_kunye_sayidan_AYRILMADI(self, ad):
        """Sayı taşındıysa künyesi de aynı sözlükte olmalı."""
        ozet = _ozet(ad)
        ciftler = [
            ('geometry_summary', 'wall_thickness_mm', 'wall_thickness_source'),
            ('geometry_summary', 'nozzle_wall_thickness_mm',
             'nozzle_wall_thickness_source'),
            ('material_summary', 'chamber_mass_density_kg_m3',
             'chamber_mass_density_source'),
            ('material_summary', 'nozzle_mass_density_kg_m3',
             'nozzle_mass_density_source'),
        ]
        for sozluk, sayi, kunye in ciftler:
            blok = ozet[sozluk]
            assert sayi in blok and kunye in blok, (ad, sozluk, sayi, kunye)
            if blok[sayi] is not None:
                assert isinstance(blok[kunye], str) and blok[kunye].strip(), (
                    f'{ad}: {sozluk}.{sayi} yayımlanıyor ama künyesi boş')


class TestP15B412TasinanSayiKUTLEYIURETIYOR:
    """Taşınan sayılar SÜS DEĞİL: kamara kütlesi onlardan yeniden kurulur.

    Alanı başka bir sözlüğe kopyalayıp kütleyi başka girdiyle hesaplamak
    da "mass_breakdown yalnız kütle taşır" testini yeşillendirirdi. Bu
    bekçi o kaçışı kapatır: yayımlanan cidar ve yayımlanan yoğunlukla
    kabuk hacmi çarpımı, yayımlanan kamara kütlesini VERMELİDİR
    (``_estimate_component_mass`` ile aynı hacim modeli:
    V = pi x L x (r_dis^2 - r_ic^2), cidar iç çapın DIŞINA eklenir).
    """

    @pytest.mark.parametrize('ad', P09_FIKSTURLERI)
    def test_kamara_kutlesi_yayimlanan_cidar_ve_yogunluktan_kurulur(self, ad):
        from hrma.export.cad_visualization import _real_scalar
        md = _fixture(ad)
        ozet = _ozet(ad)
        cidar_mm = ozet['geometry_summary']['wall_thickness_mm']
        rho = ozet['material_summary']['chamber_mass_density_kg_m3']
        cap = _real_scalar(md.get('chamber_diameter'))
        boy = _real_scalar(md.get('chamber_length'))
        if cidar_mm is None or rho is None:
            pytest.skip(f'{ad}: koşum cidar/yoğunluk yayımlamıyor')
        if cap is None or boy is None:
            # Üreteç kendi yedek boyutunu kullanır; o yedeği burada
            # KOPYALAMAK tek kaynağı bozardı (ÖK-04). Bu motorda türetim
            # yapılmaz, gerekçe ADIYLA yazılır.
            pytest.skip(f'{ad}: fikstür chamber_diameter/chamber_length '
                        f'yayımlamıyor (cap={cap!r}, boy={boy!r})')
        ic_r = cap / 2.0
        dis_r = ic_r + cidar_mm / 1000.0
        beklenen = math.pi * boy * (dis_r ** 2 - ic_r ** 2) * rho
        assert ozet['mass_breakdown']['chamber_mass'] == pytest.approx(
            beklenen, rel=1e-9), (
            f'{ad}: yayımlanan cidar/yoğunluk kamara kütlesini vermiyor — '
            'sayılar ayrışmış (taşıma değil kopya)')


class TestP15B412YonTarifiTAZE:
    """``mass_inputs_note`` uydurma yol yazamaz: her yol gövdede çözülür."""

    YOL_DESENI = re.compile(
        r'(geometry_summary|material_summary)\s*\.\s*([A-Za-z0-9_]+)')

    @pytest.mark.parametrize('ad', P09_FIKSTURLERI)
    def test_notta_anilan_her_yol_govdede_var(self, ad):
        ozet = _ozet(ad)
        not_metni = ozet['mass_breakdown']['mass_inputs_note']
        assert not_metni and isinstance(not_metni, str)
        anilan = set(self.YOL_DESENI.findall(not_metni.replace('\n', '')))
        assert anilan, 'yön tarifi hiçbir alanı adıyla anmıyor'
        cozulmeyen = [(s, a) for s, a in anilan
                      if a not in ozet.get(s, {})]
        assert cozulmeyen == [], (
            f'{ad}: yön tarifi olmayan alanı gösteriyor: {cozulmeyen}')

    @pytest.mark.parametrize('ad', P09_FIKSTURLERI)
    def test_tasinan_her_alan_notta_ANILIYOR(self, ad):
        not_metni = _ozet(ad)['mass_breakdown']['mass_inputs_note'].replace(
            '\n', '')
        anilan = {a for _s, a in self.YOL_DESENI.findall(not_metni)}
        eksik = [a for alanlar in TASINAN.values() for a in alanlar
                 if a not in anilan]
        assert eksik == [], f'{ad}: yön tarifinde anılmayan taşınmış alan: {eksik}'
