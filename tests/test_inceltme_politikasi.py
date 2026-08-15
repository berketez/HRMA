"""
Yön-ayrışık inceltme politikası bekçileri (hrma/fea/structural_axisym.py,
``solve_with_refinement`` ``refine_policy`` sözleşmesi).

Kilitlenen kusur (ÖLÇÜLDÜ, 2026-08-15, parti 24 bulgusu): eski sürücü her
turda eksenel VE radyal bölümü REFINE_FACTOR ile birlikte katlıyordu
(eleman tur başına F² kat). Yönler farklı hızda yakınsadığı için bu eleman
israf eder — ölçülen örnekler:

* Lamé silindiri (z'den bağımsız çözüm): birlikte katlama 3072 elemanda
  yakınsıyor; yön-ayrışık politika 4 kararın 4'ünde de radyalı seçip 192
  elemanda AYNI analitik doğrulukla (%0,023) yakınsıyor — 16 kat tasarruf.
* Sıvı deterministik vakası (tol=0,05): birlikte katlama 16384 elemanda
  (6,7 s), yön-ayrışık 4096 elemanda (0,6 s) yakınsıyor — 4 kat tasarruf.
* Aynı bütçede (max_rounds=4) iki politika sıvı vakasında aynı (256, 64)
  mesh'ine varıyor; yön-ayrışık hüküm ölçütü %2,6 (eskisi %4,6) — hüküm
  aynı elemanla DAHA isabetli ölçülüyor (gösterge ayrıştırması).

Sözleşme:

1. Yön kararı ÖLÇÜLEBİLİR ve history'de BEYANLI: her turda iki sonda
   (yalnız eksenel katlanmış, yalnız radyal katlanmış) çözülür; büyük
   gösterge yönü kabul edilir. ``history[k]['karar']`` d_eksenel, d_radyal,
   d_secilen, toplam, iki sondanın kimliği ve gerekçe metnini taşır.
2. ``rel_change`` her iki politikada toleransla karşılaştırılan büyüklüğün
   KENDİSİDİR (directional'da gösterge TOPLAMI — birlikte-katlama farkının
   birinci-mertebe karşılığı; yalnız max(d) eski ölçütten gevşek olurdu).
   ``converged ⟺ final_rel_change < tol`` ve
   ``final_rel_change == history[-1]['rel_change']``.
3. Tur bütçesi: ``max_rounds`` eski politikanın eleman TAVANINI tanımlar;
   directional aynı tavan içinde en fazla ``2·max_rounds`` tek-yön
   katlaması yapar (eleman tavanı aşılmaz — app.py FEA_MAX_ELEMS bütçe
   hesabı geçerli kalır).
4. Geriye uyum: ``refine_policy="joint"`` eski birlikte-katlamayı BİREBİR
   üretir (grid dizisi ve sayılar değişmez); alan adları korunur, yeni
   alanlar (yon/karar, meta.refine_policy/n_solves) eklemseldir.

Mutasyon sözleşmesi (md5'li kanıtlar oturum raporunda):
* Karar karşılaştırması ters çevrilirse (küçük gösterge yönü seçilirse)
  Lamé bekçisi (4/4 radyal) ve sıvı karar-tutarlılık bekçisi kırmızı.
* Yakınsama ölçütü toplam yerine max(d) yapılırsa rel_change==toplam
  bekçisi ve sıvı eleman kilidi kırmızı.
"""

import numpy as np
import pytest

from hrma.fea import bridge
from hrma.fea.structural_axisym import (
    DEFAULT_REFINE_POLICY,
    Material,
    REFINE_FACTOR,
    REFINE_POLICIES,
    REFINE_POLICY_DIRECTIONAL,
    REFINE_POLICY_JOINT,
    solve_with_refinement,
)

pytestmark = pytest.mark.filterwarnings('ignore::RuntimeWarning')

# ---------------------------------------------------------------------------
# Lamé silindiri — tests/fea/test_yapisal_dogrulama.py ile aynı problem
# tanımı (oradan import edilmez: test dosyaları arası import kırılgandır;
# değerler tek kaynaktan — Timoshenko & Goodier Böl. 4 — türetilir).
# ---------------------------------------------------------------------------
LAME_A, LAME_T, LAME_L, LAME_P = 0.05, 0.025, 0.10, 10.0e6
STEEL = Material(E=200.0e9, nu=0.3, yield_strength=250.0e6, name='test-steel')


def _lame_vm_plane_strain(r, a, b, p, nu):
    A = p * a * a / (b * b - a * a)
    sr = A * (1.0 - (b * b) / (r * r))
    st = A * (1.0 + (b * b) / (r * r))
    sz = nu * (sr + st)
    return np.sqrt(0.5 * ((sz - sr) ** 2 + (sr - st) ** 2 + (st - sz) ** 2))


def _kos_lame(**kw):
    kw.setdefault('max_rounds', 5)
    return solve_with_refinement(
        [(0.0, LAME_A), (LAME_L, LAME_A)], LAME_T, STEEL, LAME_P,
        axial_fix='both_ends', n_axial0=4, n_radial0=3, **kw)


@pytest.fixture(scope='module')
def sivi_girdileri():
    """Sıvı deterministik vakasının köprü-çıkarımlı girdileri.

    test_mesh_disyuzey_egrilik_tabani.py'deki RocketCEA'sız kurulumun
    aynısı; politika karşılaştırması çözücü seviyesinde yapıldığı için
    girdiler ``extract_structural_inputs`` ile bir kez çıkarılır.
    """
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    pts_mm, _meta = sample_nozzle_inner_contour({
        'chamber_diameter': 0.0825,
        'throat_diameter': 0.0285,
        'exit_diameter': 0.0995,
    })
    motor = {
        'chamber_pressure': 100.0,
        'chamber_length': 150.0,
        'nozzle_contour': {
            'points': [[z / 1000.0, r / 1000.0] for z, r in pts_mm]},
        'structural_analysis': {'chamber_structure': {
            'wall_thickness': 2.0,
            'wall_thickness_source': 'test sabiti',
            'material_key': 'inconel_718',
            'yield_strength': 1100.0,
        }},
    }
    inp = bridge.extract_structural_inputs(motor)
    assert inp['status'] == bridge.BRIDGE_STATUS_OK
    return inp


def _kos_sivi(inp, **kw):
    return solve_with_refinement(
        inp['contour'], inp['thickness_m'], inp['material'],
        inner_pressure=inp['inner_pressure_pa'], **kw)


# ---------------------------------------------------------------------------
# 1) Karar beyanı ve karar tutarlılığı — sıvı vakası (her iki yön de seçilir)
# ---------------------------------------------------------------------------
class TestKararBeyani:

    @pytest.fixture(scope='class')
    def sivi(self, sivi_girdileri):
        # tol=0,05: ölçülen yol [eksenel×3, radyal×2, eksenel] → (256, 16)
        # elemanda yakınsar; her iki yön de kararlarda görülür.
        return _kos_sivi(sivi_girdileri, tol=0.05)

    def test_politika_ve_cozum_sayisi_beyanli(self, sivi):
        assert DEFAULT_REFINE_POLICY == REFINE_POLICY_DIRECTIONAL
        assert sivi.meta['refine_policy'] == REFINE_POLICY_DIRECTIONAL
        # Her kabul edilen tur 2 sonda çözer + başlangıç çözümü.
        assert sivi.meta['n_solves'] == 1 + 2 * (len(sivi.history) - 1)
        assert 'yön-ayrışık' in sivi.meta['_basis']

    def test_ilk_kayit_karar_tasimaz(self, sivi):
        h0 = sivi.history[0]
        assert h0['rel_change'] is None
        assert h0['yon'] is None and h0['karar'] is None

    def test_her_karar_olculu_ve_gerekceli(self, sivi):
        """Karar = büyük gösterge; kabul edilen mesh = o yönün sondası."""
        for onceki, h in zip(sivi.history, sivi.history[1:]):
            k = h['karar']
            assert h['yon'] in ('eksenel', 'radyal')
            for alan in ('d_eksenel', 'd_radyal', 'd_secilen', 'toplam',
                         'sonda_eksenel', 'sonda_radyal', 'gerekce'):
                assert alan in k, f'karar alanı eksik: {alan}'
            # Yön, göstergelerin ölçülen büyüklük sırasından gelir
            # (eşitlikte eksenel) — karşılaştırma mutasyonunun bekçisi.
            beklenen_yon = ('eksenel' if k['d_eksenel'] >= k['d_radyal']
                            else 'radyal')
            assert h['yon'] == beklenen_yon, k['gerekce']
            assert k['d_secilen'] == max(k['d_eksenel'], k['d_radyal'])
            # rel_change toleransla karşılaştırılan büyüklüğün kendisi:
            # gösterge TOPLAMI (max(d) mutasyonunun bekçisi).
            assert k['toplam'] == pytest.approx(
                k['d_eksenel'] + k['d_radyal'], rel=1e-12)
            assert h['rel_change'] == k['toplam']
            # Sondalar önceki kabul edilen mesh'in tek-yön katlanmışıdır;
            # kabul edilen kayıt seçilen sondanın kendisidir.
            assert (k['sonda_eksenel']['n_axial']
                    == REFINE_FACTOR * onceki['n_axial'])
            assert k['sonda_eksenel']['n_radial'] == onceki['n_radial']
            assert k['sonda_radyal']['n_axial'] == onceki['n_axial']
            assert (k['sonda_radyal']['n_radial']
                    == REFINE_FACTOR * onceki['n_radial'])
            secilen = k['sonda_' + h['yon']]
            assert (h['n_axial'], h['n_radial'], h['max_von_mises']) == (
                secilen['n_axial'], secilen['n_radial'],
                secilen['max_von_mises'])
            assert k['gerekce'].strip()

    def test_sivi_vakasinda_iki_yon_de_secilir(self, sivi):
        """Ölçüldü: boğaz tepesi iki yönde de çözünürlük istiyor.

        'Hep aynı yönü katla' mutasyonları (karar ölçümünün koparılması)
        burada kırmızı verir.
        """
        yonler = {h['yon'] for h in sivi.history[1:]}
        assert yonler == {'eksenel', 'radyal'}

    def test_final_rel_change_son_kaydin_olcusudur(self, sivi):
        assert sivi.final_rel_change == sivi.history[-1]['rel_change']
        assert sivi.converged is (sivi.final_rel_change < sivi.tol)


# ---------------------------------------------------------------------------
# 2) Yön ayrımının ölçülebilirliği — z'den bağımsız problem eksenel eleman
#    YAKMAZ (Lamé silindiri; analitik doğruluk değişmez)
# ---------------------------------------------------------------------------
class TestLameYonAyrimi:

    @pytest.fixture(scope='class')
    def yonlu(self):
        return _kos_lame()

    def test_tum_kararlar_radyal(self, yonlu):
        """Çözüm z'den bağımsız → d_eksenel ≈ 0; eksenel katlama israftır.

        Ölçüldü: d_eksenel < 1e-9, d_radyal ilk turda 0,053. Karar
        karşılaştırması ters çevrilirse (küçük gösterge seçilirse) bu
        bekçi kırmızı verir.
        """
        assert all(h['yon'] == 'radyal' for h in yonlu.history[1:])
        for h in yonlu.history[1:]:
            assert h['karar']['d_eksenel'] < 1e-6
            assert h['karar']['d_radyal'] > 1e-3
        assert yonlu.mesh.n_axial == 4          # başlangıçtaki değerde kaldı

    def test_eleman_tasarrufu_olculen_esikte(self, yonlu):
        """Ölçüldü: birlikte katlama 3072 elemanda, yön-ayrışık 192'de
        yakınsıyor (16 kat). Eşik ölçümden: en az 8 kat tasarruf."""
        birlikte = _kos_lame(refine_policy=REFINE_POLICY_JOINT)
        assert birlikte.converged and yonlu.converged
        assert yonlu.mesh.n_elems == 192
        assert birlikte.mesh.n_elems == 3072
        assert yonlu.mesh.n_elems * 8 <= birlikte.mesh.n_elems

    def test_analitik_dogruluk_degismez(self, yonlu):
        """Yakınsamış çözüm Lamé analitiğine < %2 (V2.7 şartı); ölçülen
        %0,023 — anizotrop (4×48) mesh SPR doğruluğunu bozmuyor."""
        b = LAME_A + LAME_T
        vm_ana = float(_lame_vm_plane_strain(LAME_A, LAME_A, b, LAME_P,
                                             STEEL.nu))
        vm_nod = float(yonlu.result.von_mises_nodal.max())
        assert abs(vm_nod - vm_ana) / vm_ana < 0.0025   # ölçülen 10 katı pay
        assert yonlu.final_rel_change < yonlu.tol


# ---------------------------------------------------------------------------
# 3) Geriye uyum — joint politikası eski davranışı birebir üretir
# ---------------------------------------------------------------------------
class TestJointGeriyeUyum:

    @pytest.fixture(scope='class')
    def joint(self):
        return _kos_lame(refine_policy=REFINE_POLICY_JOINT)

    def test_grid_dizisi_eski_politikanin_aynisi(self, joint):
        """Eski sürücünün deterministik dizisi: her turda İKİ yön katlanır."""
        grid = [(h['n_axial'], h['n_radial']) for h in joint.history]
        assert grid == [(4, 3), (8, 6), (16, 12), (32, 24), (64, 48)]
        assert all(h['yon'] == 'eksenel+radyal' and h['karar'] is None
                   for h in joint.history[1:])

    def test_sayisal_sonuc_eski_taban_olcumuyle_ayni(self, joint):
        """Politika parametresi eklenirken joint yolu SAYISAL değişmedi
        (taban ölçümü 2026-08-15: final_rel_change = 0,0070723731)."""
        assert joint.converged
        assert joint.final_rel_change == pytest.approx(0.0070723731,
                                                       rel=1e-6)
        assert joint.meta['refine_policy'] == REFINE_POLICY_JOINT
        assert joint.meta['n_solves'] == len(joint.history)
        assert 'birlikte-katlama' in joint.meta['_basis']


# ---------------------------------------------------------------------------
# 4) Sıvı vakasında eş-hüküm eleman tasarrufu (ölçümden eşik)
# ---------------------------------------------------------------------------
class TestSiviElemanTasarrufu:

    def test_ayni_toleransta_daha_az_elemanla_yakinsar(self, sivi_girdileri):
        """Ölçüldü (tol=0,05, max_rounds=4): joint 16384 elemanda (6,7 s),
        directional 4096 elemanda (0,6 s) yakınsıyor; tepe von Mises
        636,6 MPa (joint 662,2 — fark %3,9, iki hüküm de kendi %5
        toleransının içinde). Eşikler ölçümden; yakınsama ölçütü max(d)'ye
        gevşetilirse eleman kilidi kırmızı verir (daha erken durur)."""
        yeni = _kos_sivi(sivi_girdileri, tol=0.05)
        assert yeni.converged
        assert yeni.mesh.n_elems == 4096
        assert (yeni.mesh.n_axial, yeni.mesh.n_radial) == (256, 16)
        assert yeni.result.max_von_mises == pytest.approx(636.6e6, rel=0.02)
        # Joint aynı toleransta 4 kat elemana ihtiyaç duyuyor (ölçüldü);
        # bekçi eşiği en az 2 kat.
        eski = _kos_sivi(sivi_girdileri, tol=0.05,
                         refine_policy=REFINE_POLICY_JOINT)
        assert eski.converged
        assert eski.mesh.n_elems == 16384
        assert yeni.mesh.n_elems * 2 <= eski.mesh.n_elems


# ---------------------------------------------------------------------------
# 5) Sözleşme uçları — bütçe, tavan, geçersiz girdi, tek tur
# ---------------------------------------------------------------------------
class TestSozlesmeUclari:

    def test_gecersiz_politika_reddedilir(self):
        with pytest.raises(ValueError, match='refine_policy'):
            _kos_lame(refine_policy='ikisi-birden')
        assert set(REFINE_POLICIES) == {REFINE_POLICY_DIRECTIONAL,
                                        REFINE_POLICY_JOINT}

    def test_tek_tur_denetlenemedi_beyani(self):
        ref = _kos_lame(max_rounds=0)
        assert len(ref.history) == 1
        assert ref.converged is False
        assert ref.final_rel_change is None
        assert 'YAKINSAMA DENETLENEMEDİ' in ref.meta['beyan']

    def test_butce_ve_eleman_tavani(self, sivi_girdileri):
        """max_rounds=1 → en fazla 2 tek-yön katlaması; eleman tavanı eski
        politikanın 1 turluk tavanı (n0·F²) — app bütçe hesabı geçerli."""
        ref = _kos_sivi(sivi_girdileri, max_rounds=1)
        n0 = ref.history[0]['n_elems']
        assert len(ref.history) <= 3
        assert ref.mesh.n_elems <= n0 * REFINE_FACTOR ** 2
        assert not ref.converged            # bu vakada 2 katlama yetmez
        assert 'YAKINSAMADI' in ref.meta['beyan']
        assert 'eleman' in ref.meta['beyan']

    def test_beyan_yon_ozetini_tasir(self):
        ref = _kos_lame()
        assert 'radyal katlama' in ref.meta['beyan']
        assert str(ref.mesh.n_elems) in ref.meta['beyan']
        sayac = ref.meta['yon_katlama_sayilari']
        assert sayac['radyal'] == len(ref.history) - 1
        assert sayac['eksenel'] == 0
