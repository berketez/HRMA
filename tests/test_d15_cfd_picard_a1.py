# -*- coding: utf-8 -*-
"""D15 / cfd-picard — Picard öz-tutarlılık kapısının PLATO sözleşmesi.

KAPATILAN KUSUR (ÖH defter OH-Z5-14)
------------------------------------
Örtük yolun öz-tutarlılık kapısı (``scheme_residual_blocks_verdict``)
doğru soruyu soruyor — "hüküm ŞEMANIN kendi kalıntısıyla da kazanıldı
mı?" — ama viskoz/ayrılmalı vaka sınıfında sorunun cevabı YOK: minmod
canlı bir LİMİT DÖNGÜSÜNDEDİR ve şema kalıntısı bütçe büyütülerek
inmez. ÖLÇÜLDÜ (2026-08-28, viskoz aşırı-genişlemiş 64×16 lüle,
tol 1e-8; ``docs/scofield/raw/OH/Z5S/pk3/ayrilma_ulasilabilirlik.json``):
5.000 / 10.000 / 20.000 iterasyon tavanlarında şema kalıntısı
1,2204e-04 / 1,2168e-04 / 1,2206e-04 — dört katına çıkan bütçe sayıyı
binde üç bile oynatmadı.

Ürün bunu KULLANICIYA SÖYLEMİYORDU: elde yalnız ``converged=False``
vardı ve "biraz daha iterasyon ver" ile "bu vaka sınıfında hedef
ULAŞILAMAZ" birbirinden ayrılamıyordu. Hedef GEVŞETİLMEDİ (kapı yerinde,
hüküm hâlâ kazanılmamış); eklenen şey PLATO TESPİTİDİR:
``convergence_status='plateau'`` + ``convergence_plateau`` bloğu
(plateau_residual / target_residual / pencere / göreli yayılım /
ÖRNEKLER) ve panelin bunları BASMASI.

BU DOSYA NEYİ TUTAR
-------------------
  1. ``_plateau_verdict`` aritmetiği — ölçülen gerçek seriyle: plato
     DOĞRU seride tespit edilir, inen seride ve hedefin altına inen
     seride EDİLMEZ, yetersiz örnek/dar pencere ADIYLA reddedilir.
  2. Çözücünün durum alanı: ``convergence_status`` dört değerden biri
     ve ``converged`` ile TUTARLI; ``convergence_plateau`` her koşuda
     (plato olmasa da) gerekçesiyle döner.
  3. Panel: uç bu alanları yayımlıyor ve ``cfd_panel.js`` onları
     GERÇEKTEN basıyor (D15-CFD-01 — ters yön sözleşmesi).
"""
import json
import math
import os

import numpy as np
import pytest

from hrma.cfd.steady import (DEFAULT_SCHEME_PLATEAU_REL_TOL,
                             DEFAULT_SCHEME_PROBE_EVERY,
                             SCHEME_PLATEAU_MIN_SAMPLES,
                             _plateau_verdict, solve_steady_axisym)

from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_PB, LULE_R,
                                LULE_T0, lule_gridi)
from tests.support.kanit import kanit_gerekli

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: PK3'ün ULAŞILABİLİRLİK ölçümü — plato serisinin TEK KAYNAĞI. Sayılar
#: bu dosyaya YENİDEN YAZILMAZ; ölçüm dosyasından okunur ki bekçi ile
#: kanıt sessizce ayrışamasın.
PK3_OLCUM = os.path.join(REPO, 'docs', 'scofield', 'raw', 'OH', 'Z5S',
                         'pk3', 'ayrilma_ulasilabilirlik.json')


def olculen_plato_serisi():
    """(iterasyon, şema kalıntısı) — PK3 ölçümünün kendi sayıları."""
    with open(kanit_gerekli(PK3_OLCUM), encoding='utf-8') as f:
        ham = json.load(f)
    seri = []
    for anahtar, kayit in ham.items():
        seri.append((int(anahtar.split('_')[1]),
                     float(kayit['sema_kalinti_bagimsiz'])))
    return sorted(seri)


class TestPlatoAritmetigi:
    """``_plateau_verdict`` — hüküm KAZANDIRMAZ, "bütçe geçmez" der."""

    def test_olculen_seride_PLATO_tespit_edilir(self):
        seri = olculen_plato_serisi()
        assert len(seri) >= SCHEME_PLATEAU_MIN_SAMPLES, (
            f'PK3 ölçümü {SCHEME_PLATEAU_MIN_SAMPLES} örnekten az taşıyor; '
            f'plato hükmü bu seriyle sınanamaz: {PK3_OLCUM}')
        h = _plateau_verdict(seri, 1e-8)
        assert h['detected'] is True, h['reason']
        assert h['plateau_residual'] == pytest.approx(seri[-1][1], rel=1e-12)
        assert h['target_residual'] == 1e-8
        assert h['window_iterations'] == seri[-1][0] - seri[-3][0]
        # Ölçümün kendi hükmü: dört katına çıkan bütçe binde üçten az
        # oynattı — eşiğin (%1) ALTINDA, yani "durdu".
        assert 0.0 < h['relative_spread'] < DEFAULT_SCHEME_PLATEAU_REL_TOL
        assert h['samples'] == [[i, v] for i, v in seri[-3:]]

    def test_inen_seride_plato_YOK(self):
        # Gerçekten yakınsayan bir koşuda kalıntı pencere başına mertebe
        # düşer; bu seri plato SAYILMAMALIDIR.
        seri = [(5000, 1.2e-4), (10000, 1.2e-6), (20000, 1.2e-8)]
        h = _plateau_verdict(seri, 1e-9)
        assert h['detected'] is False
        assert 'yayılım' in h['reason']

    def test_hedefin_ALTINA_inen_seri_plato_DEGIL(self):
        # Aynı bantta ama hedefin altında: bu yakınsamadır, plato değil —
        # "plato" damgası hükmü yanlış yere taşırdı.
        seri = [(5000, 1.0e-9), (10000, 1.0e-9), (20000, 1.0e-9)]
        h = _plateau_verdict(seri, 1e-8)
        assert h['detected'] is False
        assert 'hedefin altına' in h['reason']

    def test_yetersiz_ornek_ADIYLA_reddedilir(self):
        h = _plateau_verdict([(5000, 1.2e-4), (10000, 1.2e-4)], 1e-8)
        assert h['detected'] is False and 'örnek yetersiz' in h['reason']
        assert h['plateau_residual'] is None

    def test_dar_pencere_ADIYLA_reddedilir(self):
        # Üç ölçüm arka arkaya düşerse "N iterasyon boyunca durdu"
        # denemez: pencere en az bir örnekleme periyodu KAPSAMALI.
        dar = [(1000, 1.2e-4), (1001, 1.2e-4), (1002, 1.2e-4)]
        h = _plateau_verdict(dar, 1e-8)
        assert h['detected'] is False and 'pencere dar' in h['reason']
        assert h['window_iterations'] == 2

    def test_sonsuz_deger_plato_SAYILMAZ(self):
        seri = [(1000, 1.2e-4), (2000, 1.2e-4), (3000, float('inf'))]
        h = _plateau_verdict(seri, 1e-8)
        assert h['detected'] is False and 'sonlu olmayan' in h['reason']


@pytest.fixture(scope='module')
def hizli_kosum():
    """Kaba Euler koşusu (30×8, 1. mertebe) — durum alanının kablosu.

    Amaç plato ÜRETMEK değil, her koşuda dönen sözleşmeyi (durum alanı +
    plato bloğu + gerekçe) hızlı doğrulamaktır.
    """
    grid = lule_gridi(30, 8)
    return solve_steady_axisym(grid, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R,
                               Pb=LULE_PB, second_order=False,
                               max_iters=4000, tol_res=1e-8,
                               settle_tol=1e-9)


class TestCozucuDurumAlani:
    """``convergence_status`` — hükümsüzlüğün CİNSİ makine-okur."""

    DURUMLAR = ('converged', 'plateau', 'not_converged', 'diverged')

    def test_durum_dort_degerden_biri_ve_hukumle_tutarli(self, hizli_kosum):
        d = hizli_kosum['convergence_status']
        assert d in self.DURUMLAR, d
        assert (d == 'converged') is bool(hizli_kosum['converged'])

    def test_plato_blogu_HER_kosumda_gerekcesiyle_doner(self, hizli_kosum):
        p = hizli_kosum['convergence_plateau']
        for ad in ('detected', 'plateau_residual', 'target_residual',
                   'relative_spread', 'window_iterations', 'samples',
                   'rel_tol', 'min_samples', 'probe_every', 'reason'):
            assert ad in p, f'plato bloğunda {ad} yok'
        assert p['reason'], 'plato hükmü gerekçesiz döndü'
        assert p['rel_tol'] == DEFAULT_SCHEME_PLATEAU_REL_TOL
        assert p['probe_every'] == DEFAULT_SCHEME_PROBE_EVERY
        assert p['min_samples'] == SCHEME_PLATEAU_MIN_SAMPLES
        # Hedef, koşumun KENDİ eşiğidir — ikinci bir sayı uydurulmaz.
        assert p['target_residual'] == 1e-8

    def test_yakinsamayan_kosum_CONVERGED_DEMEZ(self):
        """Tavana dayanan koşuda durum 'converged' OLAMAZ.

        M4 mutasyonu (2026-08-31) bu bekçiyi doğurdu: yalnız yakınsayan
        bir koşuyla sınandığında ``convergence_status`` atamasının
        yakınsamayan DALINI hiçbir bekçi görmüyordu — mutasyon
        (``not_converged`` → ``converged``) YEŞİL geçti. Kısa tavanlı
        koşu o dalı kapsar.
        """
        grid = lule_gridi(30, 8)
        s = solve_steady_axisym(grid, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R,
                                Pb=LULE_PB, second_order=False,
                                max_iters=120, tol_res=1e-14,
                                settle_tol=1e-15)
        assert s['converged'] is False, 'vaka kurulamadı: koşu yakınsadı'
        assert s['convergence_status'] in ('plateau', 'not_converged'), (
            f"tavana dayanan koşu '{s['convergence_status']}' beyan etti")

    def test_ornekler_ARTAN_iterasyonda_ve_gercek(self, hizli_kosum):
        p = hizli_kosum['convergence_plateau']
        it = [int(s[0]) for s in p['samples']]
        assert it == sorted(set(it)), f'örnekler artan/tekil değil: {it}'
        assert all(i <= int(hizli_kosum['iterations']) for i in it)
        assert all(math.isfinite(float(s[1])) for s in p['samples'])

    def test_ornekleme_ALANI_DEGISTIRMEZ(self):
        """Plato örneklemesi gözlemdir: aynı ayar → BİT-AYNI alan.

        Örnekleme U'ya geri beslenseydi §11.3 bit-özdeşlik sözleşmesi ve
        iterasyon sayıları kayardı. İki koşum aynı tohumdan gider.
        """
        grid = lule_gridi(30, 8)
        ortak = dict(P0=LULE_P0, T0=LULE_T0, gamma=LULE_GAMMA, R=LULE_R,
                     Pb=LULE_PB, second_order=False, max_iters=1200,
                     tol_res=1e-12, settle_tol=1e-13)
        a = solve_steady_axisym(grid, **ortak)
        b = solve_steady_axisym(grid, **ortak)
        assert a['iterations'] == b['iterations']
        assert np.array_equal(a['fields']['rho_kg_m3'],
                              b['fields']['rho_kg_m3'])
