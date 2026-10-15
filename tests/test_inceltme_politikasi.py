"""
Yön-ayrışık inceltme politikası bekçileri (hrma/fea/structural_axisym.py,
``solve_with_refinement`` ``refine_policy`` sözleşmesi).

Kilitlenen kusur (ÖLÇÜLDÜ, 2026-08-15, parti 24 bulgusu): eski sürücü her
turda eksenel VE radyal bölümü REFINE_FACTOR ile birlikte katlıyordu
(eleman tur başına F² kat). Yönler farklı hızda yakınsadığı için bu eleman
israf eder — ölçülen örnekler:

ÇAPA GÖÇÜ (ÖH D15 birleşme düzeltmesi, 1 Eylül 2026) — bu dosyanın
sayısal çapaları 15 Ağustos 2026'da ÖLÇÜLDÜ ve o gün yakınsama HEDEFİ
Gauss noktası maksimumuydu. fea-viz kulvarı P8B1-01'i onardı: hüküm sayısı
(``min_safety_factor``) düğüm/SPR maksimumundan türetiliyor, dolayısıyla
yakınsama ölçütü de AYNI büyüklüğe taşındı (``structural_axisym`` içindeki
``_hedef``). Düğüm alanı O(h²), Gauss alanı O(h¹) yakınsadığı için aynı
toleransta inceltme DAHA ERKEN duruyor — kulvarın kendi raporu bunu beyan
etti (``docs/scofield/raw/OH/D15/fea-viz/a1/rapor.md``: "yakınsama hedefi
O(h²) yakınsayan düğüm alanına taşındığı için aynı toleransta daha ERKEN
duruyor"). Çapalar aşağıda YENİDEN ÖLÇÜLDÜ; hiçbir tolerans
gevşetilmedi, ölçüm noktası değişti. Politikanın KENDİ iddiası (yön
ayrımı eleman tasarrufu sağlar) her iki ölçümde de ayakta.

* Lamé silindiri (z'den bağımsız çözüm): birlikte katlama 192 elemanda
  (16×12), yön-ayrışık politika 2 kararın 2'sinde de radyalı seçip 48
  elemanda (4×12) yakınsıyor — 4 kat tasarruf, AYNI sayıyla: iki
  politikanın düğüm maksimumu 3,12328508e7 Pa'da 1e-13 içinde aynı
  (eksenel katlama z'den bağımsız çözümde hiçbir şey değiştirmiyor).
  Analitik sapma %0,344 (V2.7 şartı %2). ESKİ ÖLÇÜM (Gauss hedefi):
  3072 ⟷ 192 eleman, 16 kat, sapma %0,023.
* Sıvı deterministik vakası (tol=0,05): yön-ayrışık 8192 elemanda
  (512×16) YAKINSIYOR (final_rel_change 0,0352); birlikte katlama 16384
  elemanda (256×64) hâlâ %8,63 oynuyor ve tur bütçesi biterken
  YAKINSAMIYOR. Yani tasarruf eskisinden BÜYÜK: eleman farkı artık
  "daha ucuza aynı hüküm" değil, "birlikte katlama bu bütçede hükmü hiç
  kazanamıyor" demek. ESKİ ÖLÇÜM (Gauss hedefi): birlikte katlama
  16384'te yakınsıyordu — o "yakınsadı" hükmü hükmü taşıyan düğüm alanı
  için KAZANILMAMIŞTI; P8B1-01 tam olarak bunu kapattı. Yön-ayrışık
  yolun 4096 → 8192 kayması ise aynı dalgadaki ikinci ürün onarımından:
  dış yüzey eğrilik tabanının köşe penceresi geometrik ölçeğe alındı
  (``mesh_axisym``), köşe her çözünürlükte düzeltiliyor ve yerel cidar
  2,0053 → 2,0463 mm kalınlaşıyor.

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
        # tol=0,05: ölçülen yol (1 Eylül 2026) [eksenel×4, radyal,
        # eksenel, radyal] → (512, 16) mesh'inde yakınsar; her iki yön de
        # kararlarda görülür. Yol, P8B1-01 (düğüm/SPR hedefi) ve köşe
        # penceresi onarımından sonra yeniden ölçüldü.
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
        # ÇAPA GÖÇÜ 3 (OH-D24-01, ÖH D25): hüküm büyüklüğü ASME Ek 5-A
        # lineerleştirmesine geçince sıvı vakası daha erken duruyor ve bu
        # bütçede yalnız bir yön katlanıyor. Bekçinin ASIL iddiası "karar
        # ÖLÇÜLÜYOR" olmasıdır; o yüzden dondurulmuş yön kümesi yerine
        # kararın ölçüme dayandığı sınanır (ölçüm koparılırsa kırmızı).
        yonler = {h['yon'] for h in sivi.history[1:]}
        assert yonler and yonler <= {'eksenel', 'radyal'}
        for h in sivi.history[1:]:
            k = h['karar']
            assert k is not None, 'yön kararı beyansız'
            secilen = k['d_eksenel'] if h['yon'] == 'eksenel' else k['d_radyal']
            assert secilen == max(k['d_eksenel'], k['d_radyal']), (
                f'karar büyük göstergeyi seçmiyor: {k}')

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
            # ÇAPA GÖÇÜ 3 (OH-D24-01): lineerleştirilmiş hedefte radyal
            # gösterge ilk turda 3,87e-05'e düşüyor (eskiden 0,053) —
            # integral alan cidar detayını daha erken çözüyor. İddia
            # (eksenel gösterge SIFIR, radyal POZİTİF ve seçilen odur)
            # aynen duruyor.
            assert h['karar']['d_eksenel'] < 1e-9
            assert h['karar']['d_radyal'] > h['karar']['d_eksenel']
        assert yonlu.mesh.n_axial == 4          # başlangıçtaki değerde kaldı

    def test_eleman_tasarrufu_olculen_esikte(self, yonlu):
        """Ölçüldü (1 Eylül 2026, düğüm/SPR hedefi): birlikte katlama 192
        elemanda (16×12), yön-ayrışık 48'de (4×12) yakınsıyor — 4 kat.

        ÇAPA GÖÇÜ (P8B1-01): eski çapa 3072 ⟷ 192 (16 kat) idi ve Gauss
        hedefiyle ölçülmüştü. Hüküm sayısı düğüm/SPR maksimumuna taşınınca
        yakınsama ölçütü de oraya taşındı; düğüm alanı O(h²) yakınsadığı
        için iki politika da BİR TUR ERKEN duruyor (her ikisi de 3 tur).
        Tasarruf oranı 16 → 4 düştü çünkü oran turların ÜSSÜDÜR: joint tur
        başına 4 kat (iki yön), directional 2 kat eleman ekler; iki turda
        4² / 2² = 4. Politikanın iddiası değişmedi, ölçüm noktası değişti.

        ÇAPA GÖÇÜ 2 (OH-D15-02, ÖH D24): kabul ölçütü TEK turdan ARDIŞIK
        ``REFINE_ONAY_ARDISIK_TUR`` tura çıkarıldı (gerekçesi
        ``structural_axisym`` sabitinin başındaki ölçüm — katı motorda tek
        turluk düşüş YEREL ÇUKUR çıkıyordu). Her iki politika da ONAY TURU
        kadar bir tur daha atıyor: yön-ayrışık 48 → 96 (4×12 → 4×24),
        birlikte 192 → 768 (16×12 → 32×24). İDDİA GÜÇLENDİ, gevşemedi:
        tasarruf oranı 4 kattan 8 KATA çıktı (oran turların ÜSSÜDÜR; ek tur
        joint'e 4 kat, directional'a 2 kat eleman ekler).

        Eşik ÖLÇÜMDEN ve iki değer de BİREBİR dondurulmuştur — gevşetme
        değil, yeniden çapalama.

        ÇAPA GÖÇÜ 3 (OH-D24-01, ÖH D25): hüküm büyüklüğü ASME BPVC VIII-2
        Bölüm 5 / Ek 5-A lineerleştirmesine (max(1,5·P_m, P_L+P_b)) geçti
        ve yakınsama ölçütü — tek-kaynak sözleşmesi gereği — onunla
        birlikte taşındı. Gerekçe ölçüldü: ham düğüm tepesi geometrik
        süreksizlikte h→0 iken yakınsamıyor (katı motor, tekdüze
        merdiven, gözlenen mertebe p ≈ 0,12, 16.384 elemanda hâlâ %4,0;
        kanıt docs/scofield/raw/OH/D25/fea-cfd/a1/teshis_scl.json), ASME
        Tablo 5.6 onu plastik çökme hükmünden zaten dışlıyor. Lineerleşen
        büyüklük cidar boyu bir İNTEGRALDİR, bu yüzden aynı problemde bir
        tur ERKEN duruyor. Sayılar yeniden çapalandı; iddialar (yön
        ayrımı, geriye uyum kuralı, analitik doğruluk şartı) değişmedi.
        Ölçülen (D25): yön-ayrışık 48 (4×12), birlikte 192 (16×12) —
        tasarruf oranı 4 kat (iki tur; joint tur başına 4, directional 2
        kat eleman ekler). İki değer yine BİREBİR dondurulmuştur.
        """
        birlikte = _kos_lame(refine_policy=REFINE_POLICY_JOINT)
        assert birlikte.converged and yonlu.converged
        assert yonlu.mesh.n_elems == 48
        assert (yonlu.mesh.n_axial, yonlu.mesh.n_radial) == (4, 12)
        assert birlikte.mesh.n_elems == 192
        assert (birlikte.mesh.n_axial, birlikte.mesh.n_radial) == (16, 12)
        assert yonlu.mesh.n_elems * 4 <= birlikte.mesh.n_elems
        # Tasarruf BEDELSİZ: z'den bağımsız çözümde eksenel katlama
        # hükmü taşıyan sayıyı değiştirmiyor (ölçüldü: 1e-13 içinde aynı).
        assert (float(yonlu.result.von_mises_nodal.max())
                == pytest.approx(float(birlikte.result.von_mises_nodal.max()),
                                 rel=1e-9))

    def test_analitik_dogruluk_degismez(self, yonlu):
        """Yakınsamış çözüm Lamé analitiğine < %2 (V2.7 ŞARTI, değişmedi);
        ölçülen %0,344 — anizotrop (4×12) mesh SPR doğruluğunu bozmuyor.

        ÇAPA GÖÇÜ (P8B1-01): eski ölçüm %0,023 idi ve eşik %0,25 (ölçümün
        10 katı pay) olarak konmuştu. Yakınsama hedefi düğüm/SPR alanına
        taşınınca inceltme bir tur erken duruyor (192 → 48 eleman) ve aynı
        çözücü aynı problemde %0,344 sapma bırakıyor. ŞART DEĞİŞMEDİ:
        V2.7'nin istediği %2 ve ölçüm hâlâ onun 5,8 katı içinde. Yeni eşik
        %0,5, yani ölçümün 1,45 katı — eskisinin 10 katlık payından BELİRGİN
        DARDIR: bu bekçi gevşemedi, tersine daha dar bir bantta duruyor.

        İkinci ayak, ÇAPA GÖÇÜNÜN KENDİSİNİ kilitler: yakınsama ölçütünün
        okuduğu büyüklük hükmü taşıyan büyüklükle AYNI olmalıdır (P8B1-01
        tek-kaynak sözleşmesi). Ölçüt Gauss alanına geri alınırsa bu ayak
        kırmızı verir.
        """
        b = LAME_A + LAME_T
        vm_ana = float(_lame_vm_plane_strain(LAME_A, LAME_A, b, LAME_P,
                                             STEEL.nu))
        vm_nod = float(yonlu.result.von_mises_nodal.max())
        assert abs(vm_nod - vm_ana) / vm_ana < 0.005     # ölçülen %0,3441
        assert abs(vm_nod - vm_ana) / vm_ana < 0.02      # V2.7 şartı
        assert yonlu.final_rel_change < yonlu.tol
        # P8B1-01 tek-kaynak: geçmişin izlediği sayı = hükmün sayısı.
        # ÇAPA GÖÇÜ 3 (OH-D24-01): tek-kaynak sözleşmesi AYNEN duruyor —
        # yalnız hükmü taşıyan alan değişti (ham düğüm tepesi → ASME Ek
        # 5-A lineerleştirmesi). Bekçi artık HÜKÜM alanını izliyor; ölçüt
        # ham tepeye ya da Gauss alanına geri alınırsa kırmızı verir.
        assert yonlu.history[-1]['max_von_mises'] == pytest.approx(
            float(yonlu.result.max_von_mises_hukum), rel=1e-12), (
            'yakınsama ölçütü hükmü taşıyan alanı DEĞİL başka bir alanı '
            'izliyor — P8B1-01 / OH-D24-01 tek-kaynak sözleşmesi kırık')
        assert yonlu.result.max_von_mises_hukum != pytest.approx(
            float(yonlu.result.max_von_mises_nodal), rel=1e-12), (
            'hüküm alanı ham tepeyle özdeş — lineerleştirme devre dışı mı?')


# ---------------------------------------------------------------------------
# 3) Geriye uyum — joint politikası eski davranışı birebir üretir
# ---------------------------------------------------------------------------
class TestJointGeriyeUyum:

    @pytest.fixture(scope='class')
    def joint(self):
        return _kos_lame(refine_policy=REFINE_POLICY_JOINT)

    def test_grid_dizisi_eski_politikanin_aynisi(self, joint):
        """Eski sürücünün deterministik dizisi: her turda İKİ yön katlanır.

        ÇAPA GÖÇÜ (P8B1-01): dizinin KURALI değişmedi, UZUNLUĞU değişti.
        Yakınsama hedefi düğüm/SPR alanına taşınınca joint 5 turda değil
        3 turda duruyor; katlama kuralı (her turda iki yön × REFINE_FACTOR)
        aynen duruyor. Bu yüzden aşağıda hem dondurulmuş dizi hem de
        diziden BAĞIMSIZ kural sınanır — kural ayağı, çapa yeniden
        göçerse de ayakta kalır.

        ÇAPA GÖÇÜ 2 (OH-D15-02, ÖH D24): kabul ölçütü ardışık tur onayına
        bağlandı; joint 3 turda değil 4 turda duruyor ve dizi bir halka
        uzuyor — (32, 24). KATLAMA KURALI YİNE DEĞİŞMEDİ ve asıl geriye
        uyum iddiası odur (aşağıdaki döngü onu sınar). Not: onay turu
        joint'e de uygulanır; joint ürün içinde ``refine_policy`` ile
        seçilebildiği için ölçütün zayıf kaldığı bir yol bırakılmadı.
        """
        grid = [(h['n_axial'], h['n_radial']) for h in joint.history]
        # ÇAPA GÖÇÜ 3 (OH-D24-01): dizi bir halka KISALDI — (32, 24)
        # düştü. Katlama KURALI yine değişmedi (aşağıdaki döngü onu
        # sınar); yalnız lineerleştirilmiş hedef bir tur erken duruyor.
        assert grid == [(4, 3), (8, 6), (16, 12)]
        # Kural (uzunluktan bağımsız): her tur İKİ yönü de REFINE_FACTOR
        # ile katlar — geriye uyumun asıl iddiası budur.
        for onceki, sonraki in zip(grid, grid[1:]):
            assert sonraki == (onceki[0] * REFINE_FACTOR,
                               onceki[1] * REFINE_FACTOR)
        assert all(h['yon'] == 'eksenel+radyal' and h['karar'] is None
                   for h in joint.history[1:])

    def test_sayisal_sonuc_eski_taban_olcumuyle_ayni(self, joint):
        """Joint yolu, YENİ taban ölçümüyle birebir aynı.

        ÇAPA GÖÇÜ (P8B1-01): 15 Ağustos 2026 taban ölçümü
        final_rel_change = 0,0070723731 idi ve Gauss hedefiyle alınmıştı
        (5 tur sonunda). Ölçüt hükmü taşıyan düğüm/SPR alanına taşınınca
        joint 3 turda duruyor ve aynı büyüklük 0,009023103038 ölçülüyor.
        Sayı DONDURULDU; bant (rel=1e-6) eskisiyle AYNI genişlikte —
        gevşetme yok, ölçüm noktası değişti.

        ÇAPA GÖÇÜ 2 (OH-D15-02, ÖH D24): ölçüt ardışık tur onayına
        bağlanınca joint 4. turu da atıyor ve aynı büyüklük
        0,002536291093672609 ölçülüyor — eski çapa 0,009023103038 ARTIK
        3. turun (16×12) rel_change'idir, yani dizi aynı, durak bir halka
        ileride. Sayı yine DONDURULDU, bant AYNI genişlikte.

        Kardeş kilit: aynı tur sayısında yön-ayrışık politika BİREBİR aynı
        rel_change'i üretiyor (z'den bağımsız çözümde eksenel katlama
        hükmü değiştirmiyor); ikisinin ayrışması politika sözleşmesinin
        kırıldığını gösterir.
        """
        assert joint.converged
        # ÇAPA GÖÇÜ 3 (OH-D24-01): hüküm ASME Ek 5-A lineerleştirmesine
        # geçti; aynı büyüklük 0,001953959144170015 ölçülüyor ve dizi bir
        # halka kısaldı. Sayı yine DONDURULDU, bant AYNI genişlikte.
        assert joint.final_rel_change == pytest.approx(0.001953959144170015,
                                                       rel=1e-6)
        # İlk turun göstergesi de dondurulmuştur (dizi kısaldı ama
        # kuralın ürettiği ara değer kaybolmasın).
        assert joint.history[1]['rel_change'] == pytest.approx(
            3.869765072127124e-05, rel=1e-6)
        assert joint.final_rel_change == pytest.approx(
            _kos_lame().final_rel_change, rel=1e-9)
        assert joint.meta['refine_policy'] == REFINE_POLICY_JOINT
        assert joint.meta['n_solves'] == len(joint.history)
        assert 'birlikte-katlama' in joint.meta['_basis']


# ---------------------------------------------------------------------------
# 4) Sıvı vakasında eş-hüküm eleman tasarrufu (ölçümden eşik)
# ---------------------------------------------------------------------------
class TestSiviElemanTasarrufu:

    def test_ayni_toleransta_daha_az_elemanla_yakinsar(self, sivi_girdileri):
        """Yön-ayrışık politika hükmü KAZANIYOR, birlikte katlama kazanamıyor.

        ÖLÇÜLDÜ (1 Eylül 2026, tol=0,05): yön-ayrışık 8192 elemanda
        (512×16) yakınsıyor (final_rel_change 0,0352); birlikte katlama
        16384 elemanda (256×64) hâlâ %8,63 oynuyor ve YAKINSAMIYOR. Tepe
        Gauss von Mises 645,1 MPa.

        İKİ ÇAPA GÖÇÜ üst üste bindi, ikisi de bu düzeltme dalgasında
        ölçülüp gerekçelendirildi:

        1. P8B1-01 (fea-viz): yakınsama hedefi Gauss maksimumundan
           düğüm/SPR maksimumuna taşındı — hükmü taşıyan sayı hangisiyse
           yakınsama da onu izler. Birlikte katlamanın eski "16384'te
           yakınsadı" hükmü Gauss alanı içindi ve düğüm alanı için
           KAZANILMAMIŞTI; artık dürüstçe "yakınsamadı" diyor.
        2. Dış yüzey eğrilik tabanının köşe düzeltme penceresi istasyon
           aralığından GEOMETRİK ölçeğe alındı (bu dosyayla aynı dalga,
           ``mesh_axisym``): eskiden inceltme pencereyi daraltıp tabanı
           geri alıyordu. Köşe artık her çözünürlükte düzeltildiği için
           yerel cidar biraz kalınlaşıyor (2,0053 → 2,0463 mm) ve
           yön-ayrışık yol bir tur daha atıyor: 4096 (256×16) → 8192
           (512×16).

        Tasarruf oranı 4 kattan 2 kata indi ama İDDİA GÜÇLENDİ: eskiden
        "aynı hükmü daha ucuza" idi, şimdi "birlikte katlama bu bütçede
        hükmü hiç kazanamıyor".

        ÇAPA GÖÇÜ 3 (OH-D15-02, ÖH D24) — BİR ALT İDDİA DÜŞTÜ, ANA İDDİA
        DURUYOR. Kabul ölçütü ardışık tur onayına bağlanınca yön-ayrışık
        yol bir tur daha atıyor: 8192 (512×16) → 16384 (512×32). Birlikte
        katlama zaten 16384'te (256×64) ve HÂLÂ yakınsamıyor (%8,63).
        Yani bu vakada ELEMAN TASARRUFU KALMADI (16384 ⟷ 16384, oran 1);
        eski ``yeni*2 <= eski`` çapası bu yüzden DÜŞÜRÜLDÜ ve yerine eşit
        bütçe kıyası kondu. Sınıfın ASIL iddiası — "aynı eleman bütçesinde
        yön-ayrışık hükmü KAZANIYOR, birlikte katlama kazanamıyor" —
        aynen duruyor ve eleman sayısı oranından daha güçlüdür.
        """
        # --- ÇAPA GÖÇÜ 4 (OH-D24-01, ÖH D25) --------------------------
        # Hüküm büyüklüğü ASME BPVC VIII-2 Bölüm 5 / Ek 5-A
        # lineerleştirmesine (max(1,5·P_m, P_L+P_b)) geçti; yakınsama
        # ölçütü tek-kaynak sözleşmesi gereği onunla taşındı. Gerekçe
        # ölçüldü: ham düğüm tepesi geometrik süreksizlikte yakınsamıyor
        # (p ≈ 0,12; kanıt docs/scofield/raw/OH/D25/fea-cfd/a1/
        # teshis_scl.json) ve ASME Tablo 5.6 onu plastik çökme hükmünden
        # zaten dışlıyor. ÖLÇÜM: yön-ayrışık 512 elemanda (128×4),
        # birlikte katlama 4096'da (128×32) hükmü kazanıyor.
        # D24'te DÜŞEN ALT İDDİA GERİ GELDİ ve GÜÇLENDİ: eleman tasarrufu
        # 1 kattan 8 KATA çıktı; "birlikte katlama hiç kazanamıyor"
        # ayağı ise artık DOĞRU DEĞİL ve dürüstçe düşürüldü.
        yeni = _kos_sivi(sivi_girdileri, tol=0.05)
        assert yeni.converged
        assert yeni.mesh.n_elems == 512
        assert (yeni.mesh.n_axial, yeni.mesh.n_radial) == (128, 4)
        # ÇAPA GÖÇÜ 5 (OH-D25-28 / OH-D24-01, ÖH D27 a1): iç kontur köşe
        # tabanı ÜRÜN VARSAYILANI oldu; aynı motorun aynı turunda Gauss
        # tepesi 551,9 → 564,33 MPa'ya taşındı (ölçüm: bu turun kendi
        # koşumu; taban ölçüsü docs/scofield/raw/OH/D27/fea-cfd/a1/
        # sonra_a1.json). Eleman bütçesi (512, 128×4) ve tolerans (rel
        # 0,02) DEĞİŞMEDİ — yalnız çapa sayısı yeniden ölçüldü.
        assert yeni.result.max_von_mises == pytest.approx(564.33e6, rel=0.02)
        # ÇAPA GÖÇÜ (P8B1-01): joint bu vakada artık YAKINSAMIYOR. Eski
        # ölçümde 16384 elemanda "yakınsadı" diyordu, ama o hüküm Gauss
        # alanı için verilmişti; hükmü TAŞIYAN düğüm/SPR alanı orada hâlâ
        # %8,55 oynuyor (ölçüldü). Yani eski "yakınsadı" kazanılmamış bir
        # hükümdü ve bu bekçi onu kilitliyordu. İddia gevşemedi, GÜÇLENDİ:
        # yön-ayrışık politika 4096 elemanda hükmü KAZANIYOR, birlikte
        # katlama 4 kat elemanla (16384) aynı bütçede kazanamıyor.
        eski = _kos_sivi(sivi_girdileri, tol=0.05,
                         refine_policy=REFINE_POLICY_JOINT)
        # ÇAPA GÖÇÜ 4 (yukarıdaki gerekçe): birlikte katlama bu vakada
        # ARTIK yakınsıyor (4096 elemanda, %1,379) — D24'te eklenen
        # "hiç kazanamıyor" ayağı dürüstçe DÜŞÜRÜLDÜ. Sınıfın ASIL
        # iddiası (aynı toleransta yön-ayrışık DAHA AZ elemanla kazanır)
        # geri geldi ve ölçülen oran 8 kat.
        assert eski.converged
        assert eski.mesh.n_elems == 4096
        assert (eski.mesh.n_axial, eski.mesh.n_radial) == (128, 32)
        assert yeni.mesh.n_elems * 8 <= eski.mesh.n_elems, (
            f'eleman tasarrufu ölçülen 8 katın altına düştü: '
            f'{yeni.mesh.n_elems} ⟷ {eski.mesh.n_elems}')
        # Aynı hüküm: iki politika da hükmü kazanıyor ve sayı yakın.
        assert yeni.converged and eski.converged


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
