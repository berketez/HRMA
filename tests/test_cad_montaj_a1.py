"""ÖH D37 A2 cm-0-plan — CAD montaj planı (CM-0) bekçileri.

Tasarım: ``docs/tasarim/cad-montaj/B1_tasarim.md`` §1/§3/§5.1 (B1, B2, B4,
B5 bu kademenin payı; STEP/STL/DXF/sahne bekçileri CM-1..3'te).
Kanıt: ``docs/scofield/raw/OH/A2/cm-0-plan/a1/`` (rapor, yerleşim tablosu,
ters mutasyon).

Örnek gövdeler UYGULAMANIN FORM yolundan üretilir (D35
``test_ornek_API_ve_FORM`` deseni) ve ihraç uçlarının aldığı gövdeye
indirgenir: hibrit ``currentResults.motor`` (+ ``injector`` K-1), katı/sıvı
``currentResults.motor_geometry``. Bu dosya docs/ kanıtı OKUMAZ.
"""

import copy
import hashlib
import math
import pathlib

import pytest

from hrma.export import motor_assembly as ma
from hrma.export.motor_assembly import (ASSUMED_RULES, PART_CATALOG,
                                        AssemblyPlanError, build_plan,
                                        canonical_json, part_volume_mm3,
                                        plan_signature, profile_volume_mm3,
                                        section_distance, section_overlap)

KOK = pathlib.Path(__file__).resolve().parents[1]

#: Basınç sınırı kalınlığı taşıyan ölçü adları (karar 1).
KALINLIK_OLCULERI = ('thickness_mm', 'wall_thickness_mm')


# ---------------------------------------------------------------------------
# Düzenek: üç örnek, FORM yolu
# ---------------------------------------------------------------------------
def _form_yaniti(c, yol, m):
    """Örneğin FORM yolu yanıtı.

    ``yol`` çağrı yerinde LİTERAL verilir: rota tarayıcısı (OH-D23-12,
    ``test_d18_bekci_cevirisi_a1._yardimci_parametre_baglari``) çağrıyı ancak
    böyle çözer; ``ENDPOINTS[m]`` (Subscript) kör nokta tavanını büyütüyordu
    (``test_d24_bekci_cevirisi_a1::test_cozulemeyen_cagri_tavani_asilmadi``,
    3. turda ölçüldü). Tek kaynak ``test_example_projects.ENDPOINTS`` ile
    eşitlik burada sınanır: ikinci bir uç tablosu doğmaz.
    """
    from tests.support.form_defaults import form_yuku
    from tests.test_example_projects import (ENDPOINTS, HEADERS,
                                             load_example_doc)
    assert yol == ENDPOINTS[m], (m, yol, ENDPOINTS[m])
    alanlar = load_example_doc(m)['inputs']['fields']
    r = c.post(yol, json=form_yuku(m, alanlar), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    g = r.get_json()
    assert 'error' not in g, g.get('error')
    return g


@pytest.fixture(scope='module')
def yanitlar():
    from hrma.app import app
    c = app.test_client()
    return {'hybrid': _form_yaniti(c, '/calculate', 'hybrid'),
            'solid': _form_yaniti(c, '/calculate_solid', 'solid'),
            'liquid': _form_yaniti(c, '/calculate_liquid', 'liquid')}


def _govde(yanitlar, m):
    """İhraç ucunun aldığı gövde + (hibritte) enjektör paneli."""
    y = yanitlar[m]
    if m == 'hybrid':
        return copy.deepcopy(y['motor']), copy.deepcopy(y.get('injector'))
    return copy.deepcopy(y['motor_geometry']), None


@pytest.fixture(scope='module')
def planlar(yanitlar):
    return {m: build_plan(*_govde(yanitlar, m)[:1], m,
                          injector=_govde(yanitlar, m)[1])
            for m in ('hybrid', 'solid', 'liquid')}


def _yol(d, yol):
    cur = d
    for p in yol.split('.'):
        assert isinstance(cur, dict) and p in cur, yol
        cur = cur[p]
    return cur


def _cizilen_adlar(plan):
    return sorted(p['name'] for p in plan['parts'])


def _parca(plan, pid):
    return next(p for p in plan['parts'] if p['id'] == pid)


def _cizilmeyen(plan, pid):
    return next(n for n in plan['not_modelled'] if n['id'] == pid)


# ---------------------------------------------------------------------------
# B1 — parça kümesi ve katalog kapsamı
# ---------------------------------------------------------------------------
#: Üç örnekte ÇİZİLEN parçalar (CM-F öncesi taban; B1 §7 "fizik kalemleri
#: gecikirse" satırı). Elle yazıldı: her biri raporun yerleşim tablosunda
#: yanıt alanıyla gerekçeli.
BEKLENEN_CIZILEN = {
    'hybrid': ['case_tube', 'chamber_liner_post', 'chamber_liner_pre',
               'forward_closure', 'fuel_grain', 'injector_plate',
               'nozzle_housing'],
    'solid': ['case_tube', 'forward_closure', 'grain_segment_1_of_3',
              'grain_segment_2_of_3', 'grain_segment_3_of_3',
              'nozzle_housing'],
    'liquid': ['chamber_liner_wall', 'forward_closure', 'nozzle_housing'],
}


#: Üç örnekte ÇİZİLMEYEN katalog kalemleri, (tür, katalog sınıfı) başına
#: (denetçi Ş2: rapordaki sayılar koddan; "hepsi basınç sınırı" DEĞİL —
#: new_calc_required ⟷ not_modelled/donanım ayrımı). Bölge sayısı ayrı.
BEKLENEN_CIZILMEYEN = {
    'hybrid': {('new_calc_required', 'pressure_boundary'): 3,
               ('not_modelled', 'hardware'): 4,
               ('not_modelled', 'layout'): 1},
    'solid': {('new_calc_required', 'pressure_boundary'): 2,
              ('new_calc_required', 'layout'): 2,
              ('new_calc_required', 'hardware'): 1,
              ('not_modelled', 'hardware'): 3,
              ('not_modelled', 'layout'): 2},
    'liquid': {('new_calc_required', 'pressure_boundary'): 6,
               ('new_calc_required', 'geometry'): 1,
               ('not_modelled', 'hardware'): 4,
               ('not_modelled', 'layout'): 1},
}
BEKLENEN_BOLGE = {'hybrid': 2, 'solid': 0, 'liquid': 0}


class TestB1ParcaKumesi:
    @pytest.mark.parametrize('m', ['hybrid', 'solid', 'liquid'])
    def test_cizilen_parcalar(self, planlar, m):
        assert planlar[m]['status'] == 'ok'
        assert _cizilen_adlar(planlar[m]) == BEKLENEN_CIZILEN[m]

    @pytest.mark.parametrize('m', ['hybrid', 'solid', 'liquid'])
    def test_cizilmeyen_sayisi_ve_sinifi(self, planlar, m):
        plan = planlar[m]
        sayim = {}
        for n in plan['not_modelled']:
            anahtar = (n['kind'], n['class'])
            sayim[anahtar] = sayim.get(anahtar, 0) + 1
        assert sayim == BEKLENEN_CIZILMEYEN[m]
        assert len(plan['regions']) == BEKLENEN_BOLGE[m]
        # Toplam = 8 / 10 / 12 (rapor ve Sunum 2 satırı bu sayıyı yazar).
        assert len(plan['not_modelled']) == {'hybrid': 8, 'solid': 10,
                                             'liquid': 12}[m]

    @pytest.mark.parametrize('m', ['hybrid', 'solid', 'liquid'])
    def test_katalog_bir_kez_kapsaniyor(self, planlar, m):
        plan = planlar[m]
        kimlik = ([p['id'].split('-')[0] for p in plan['parts']]
                  + [n['id'] for n in plan['not_modelled']]
                  + [r['id'] for r in plan['regions']])
        katalog = [k[0] for k in PART_CATALOG[m]]
        # Segmentler aynı katalog kimliğini paylaşır; tekilleştir.
        tekil = sorted(set(kimlik))
        assert tekil == sorted(katalog)
        cizilen_taban = {p['id'].split('-')[0] for p in plan['parts']}
        diger = [n['id'] for n in plan['not_modelled']] + \
            [r['id'] for r in plan['regions']]
        assert not (cizilen_taban & set(diger))
        assert len(diger) == len(set(diger))

    @pytest.mark.parametrize('m', ['hybrid', 'solid', 'liquid'])
    def test_profil_eksen_sirasi_x_r(self, planlar, m):
        # x (eksenel) ilk: kapak x<0'da, kasa borusu x = L'ye uzanır.
        for p in planlar[m]['parts']:
            assert p['geometry']['profile_axes'] == ['x', 'r']
        kasa = next(p for p in planlar[m]['parts']
                    if p['name'] in ('case_tube', 'chamber_liner_wall'))
        L = kasa['dims']['chamber_length_mm']['value']
        assert kasa['bbox_mm']['x_mm'][1] == L

    @pytest.mark.parametrize('m', ['hybrid', 'solid', 'liquid'])
    def test_her_cizilmeyenin_gerekcesi_var(self, planlar, m):
        for n in planlar[m]['not_modelled']:
            assert n['kind'] in ('not_modelled', 'new_calc_required')
            assert isinstance(n['reason'], str) and len(n['reason']) > 20


# ---------------------------------------------------------------------------
# B2 — ölçü ⟷ yanıt alanı bit-aynı
# ---------------------------------------------------------------------------
def _olculer(plan):
    for p in plan['parts']:
        for ad, d in p['dims'].items():
            yield p['id'], ad, d


class TestB2BitAyni:
    @pytest.mark.parametrize('m', ['hybrid', 'solid', 'liquid'])
    def test_solver_user_olcu_alanin_kendisi(self, yanitlar, planlar, m):
        govde, inj = _govde(yanitlar, m)
        if inj is not None:
            govde.setdefault('injector', inj)
        sayac = 0
        for pid, ad, d in _olculer(planlar[m]):
            src = d['source']
            if src['kind'] not in ('solver', 'user') or 'raw' not in src:
                continue
            ham = _yol(govde, src['field'])
            assert float(ham) == src['raw'], (pid, ad)
            carpan = 1000.0 if src['raw_unit'] == 'm' else 1.0
            assert d['value'] == src['raw'] * carpan, (pid, ad)
            sayac += 1
        assert sayac >= 5

    def test_elle_secilmis_alanlar(self, yanitlar, planlar):
        h = yanitlar['hybrid']['motor']
        ph = planlar['hybrid']
        assert _parca(ph, 'H01')['dims']['wall_thickness_mm']['value'] == \
            h['structural_analysis']['chamber_analysis'][
                'wall_thickness_used_mm']
        assert _parca(ph, 'H02')['dims']['thickness_mm']['value'] == \
            h['structural_analysis']['end_cap_analysis'][
                'flat_head_thickness']
        assert _parca(ph, 'H10')['dims']['wall_thickness_mm']['value'] == \
            h['nozzle_geometry']['wall_thickness']
        assert _parca(ph, 'H03')['dims']['thickness_mm']['value'] == \
            h['injector_design']['plate_thickness_mm']
        s = yanitlar['solid']['motor_geometry']
        ps = planlar['solid']
        assert _parca(ps, 'S01')['dims']['wall_thickness_mm']['value'] == \
            s['structural_analysis']['case_analysis']['wall_thickness_mm']
        assert _parca(ps, 'S05-2')['dims']['segment_gap_mm']['value'] == \
            s['grain_design']['grain_gap_mm']


# ---------------------------------------------------------------------------
# B4 — ASSUMED beyanı ve tersi (alan VARKEN assumed yazılamaz)
# ---------------------------------------------------------------------------
class TestB4AssumedBeyani:
    @pytest.mark.parametrize('m', ['hybrid', 'solid', 'liquid'])
    def test_assumed_olcu_adli_kuraldan(self, planlar, m):
        for pid, ad, d in _olculer(planlar[m]):
            if d['source']['kind'] == 'assumed':
                assert d['source']['rule'] in ASSUMED_RULES, (pid, ad)
                assert _parca(planlar[m], pid)['declared'], (pid, ad)
        for kural in planlar[m]['assumed_rules_used']:
            assert kural in ASSUMED_RULES

    @pytest.mark.parametrize('m', ['hybrid', 'solid', 'liquid'])
    def test_kural_tablosu_kullanan_parcalari_kapsar(self, planlar, m):
        # Bir kural hangi parçada kullanılıyorsa ASSUMED_RULES satırının
        # 'parts' sütunu o parçayı adıyla taşır (tek tablo, hakem #3).
        def _gez(pid, o):
            if isinstance(o, dict):
                if o.get('kind') == 'assumed' and 'rule' in o:
                    yield pid, o['rule']
                for v in o.values():
                    yield from _gez(pid, v)
            elif isinstance(o, list):
                for v in o:
                    yield from _gez(pid, v)
        kayitlar = planlar[m]['parts'] + planlar[m]['not_modelled']
        bulunan = 0
        for k in kayitlar:
            taban = k['id'].split('-')[0]
            for pid, kural in _gez(taban, k):
                if kural in ASSUMED_RULES:
                    assert pid in ASSUMED_RULES[kural]['parts'], (pid, kural)
                    bulunan += 1
        assert bulunan >= 1

    def test_hibrit_alan_varken_assumed_yok(self, planlar):
        ph = planlar['hybrid']
        assert _parca(ph, 'H07')['dims']['axial_position_mm']['source'][
            'kind'] == 'solver'
        assert _parca(ph, 'H10')['dims']['wall_thickness_mm']['source'][
            'kind'] == 'solver'
        assert _parca(ph, 'H03')['dims']['thickness_mm']['source'][
            'kind'] == 'user'
        assert 'GRAIN_AXIAL_POSITION_RULE' not in ph['assumed_rules_used']
        assert 'NOZZLE_WALL_GENERATOR_RULE' not in ph['assumed_rules_used']

    def test_hibrit_tane_on_odadan_baslar(self, yanitlar, planlar):
        pre_mm = yanitlar['hybrid']['motor']['pre_chamber_length'] * 1000.0
        assert _parca(planlar['hybrid'], 'H07')['bbox_mm']['x_mm'][0] == \
            pre_mm

    @pytest.mark.parametrize('deger', [None, 0.0])
    def test_on_oda_yoksa_ya_da_sifirsa_assumed(self, yanitlar, deger):
        g, inj = _govde(yanitlar, 'hybrid')
        if deger is None:
            g.pop('pre_chamber_length')
        else:
            g['pre_chamber_length'] = deger   # 0,0 = yayımlanmadı
        p = build_plan(g, 'hybrid', injector=inj)
        src = _parca(p, 'H07')['dims']['axial_position_mm']['source']
        assert src['kind'] == 'assumed'
        assert src['rule'] == 'GRAIN_AXIAL_POSITION_RULE'
        assert _cizilmeyen(p, 'H06')['kind'] == 'not_modelled'

    def test_lule_eti_yayimlanmazsa_adli_istisna(self, yanitlar):
        g, inj = _govde(yanitlar, 'hybrid')
        g.pop('nozzle_geometry')
        p = build_plan(g, 'hybrid', injector=inj)
        src = _parca(p, 'H10')['dims']['wall_thickness_mm']['source']
        assert src == {'kind': 'assumed',
                       'rule': 'NOZZLE_WALL_GENERATOR_RULE',
                       'basis': src['basis']}

    def test_kati_sivi_lule_eti_stepl_ayni_kural(self, planlar):
        from hrma.export.step_export import (NOZZLE_WALL_MIN_MM,
                                             NOZZLE_WALL_THROAT_FRACTION)
        # V301 CAD-2 kalem 8 — GEREKÇELİ GÜNCELLEME: örnek sıvı rejeneratif
        # ve cidarı iki katmanlı; ceket lüleyi çıkışa kadar kaplar, lüle eti
        # üreteç kuralı değil yayımlanan yığındır (STEP ile aynı kaynak).
        for m, pid in (('solid', 'S09'),):
            d = _parca(planlar[m], pid)['dims']
            dt = d['throat_diameter_mm']['source']['raw']
            assert d['wall_thickness_mm']['value'] == max(
                NOZZLE_WALL_MIN_MM, NOZZLE_WALL_THROAT_FRACTION * dt * 1000)
        d = _parca(planlar['liquid'], 'L10')['dims']['wall_thickness_mm']
        assert d['source']['kind'] == 'solver'
        assert d['source']['field'] == ('structural_analysis.chamber_structure'
                                        '.wall_stack_thickness_mm')
        assert d['value'] == d['source']['raw']


# ---------------------------------------------------------------------------
# Ş5(c) — ASSUMED değer ⟷ kural değeri bağı (denetçi D10)
# ---------------------------------------------------------------------------
def _assumed_planlari(yanitlar, planlar):
    """ASSUMED kuralların HER birini en az bir kez devreye sokan plan kümesi:
    üç örnek, ön odasız ve lüle etsiz hibrit, katı/sıvı tam yanıt ve iki
    devreli sıvı (tam yanıta test girdisi olarak plaka kalınlığı eklenir —
    ikinci devrenin 0,38 R kesri ancak böyle sınanır)."""
    out = [(f'ornek_{m}', planlar[m]) for m in ('hybrid', 'solid', 'liquid')]
    g, inj = _govde(yanitlar, 'hybrid')
    g.pop('pre_chamber_length')
    out.append(('hibrit_on_odasiz', build_plan(g, 'hybrid', injector=inj)))
    g, inj = _govde(yanitlar, 'hybrid')
    g.pop('nozzle_geometry')
    out.append(('hibrit_lule_etsiz', build_plan(g, 'hybrid', injector=inj)))
    for m in ('solid', 'liquid'):
        out.append((f'{m}_tam', build_plan(copy.deepcopy(yanitlar[m]), m)))
    t = copy.deepcopy(yanitlar['liquid'])
    t.setdefault('injector_design', {})['plate_thickness_mm'] = 6.0
    out.append(('sivi_tam_iki_devre', build_plan(t, 'liquid')))
    return out


def _kural_yeniden(plan, pid, ad, d):
    """Kuralı olan ASSUMED ölçüyü KURALIN İFADESİNDEN yeniden hesaplar.

    Sabitler tanımlandıkları modülden (``step_export``) okunur; plan
    kodu çağrılmaz. Tanınmayan kural = bekçi eksik (kırmızı).
    """
    from hrma.export import step_export as se
    kural = d['source']['rule']
    kasa = next(p for p in plan['parts']
                if p['id'] in ('S01', 'H01', 'L05'))
    L = kasa['dims']['chamber_length_mm']['value']
    if kural == 'INJECTOR_PLATE_SEAT_RULE':
        # Uyum turu (14 Eki): eski kural (boru öne uzar = plaka + 4,0 mm
        # plenum) CAD H8'de kaldırıldı; kâhin CAD'in yayımladığı tek kaynak
        # sabiti (plaka kapak iç yüzüne oturur).
        from hrma.export import cad_visualization as cv
        assert ad == 'axial_position_mm', (pid, ad)
        assert pid in ('H03', 'L01'), pid
        return float(cv.INJECTOR_PLATE_SEAT_X_MM)
    if kural == 'GRAIN_AXIAL_POSITION_RULE':
        assert ad == 'axial_position_mm', (pid, ad)
        dims = _parca(plan, pid)['dims']
        if 'segment_length_mm' in dims:
            n = dims['number_of_segments']['value']
            yigin = (n * dims['segment_length_mm']['value']
                     + (n - 1) * dims['segment_gap_mm']['value'])
        else:
            yigin = dims['grain_length_mm']['value']
        return min(se.GRAIN_AXIAL_POSITION_FRACTION
                   * max(se.GRAIN_AXIAL_MIN_SLACK_MM, L - yigin), L - yigin)
    if kural == 'NOZZLE_WALL_GENERATOR_RULE':
        assert ad == 'wall_thickness_mm', (pid, ad)
        dt = _parca(plan, pid)['dims']['throat_diameter_mm']['source']
        assert dt['raw_unit'] == 'm', dt
        return max(se.NOZZLE_WALL_MIN_MM,
                   se.NOZZLE_WALL_THROAT_FRACTION * dt['raw'] * 1000)
    pytest.fail(f'no recomputation for ASSUMED rule {kural!r} ({pid}.{ad})')


class TestAssumedDegerKuralBagi:
    def test_assumed_olcu_kural_ifadesinden(self, yanitlar, planlar):
        goruldu = set()
        for etiket, plan in _assumed_planlari(yanitlar, planlar):
            for p in plan['parts']:
                for ad, d in p['dims'].items():
                    if d['source']['kind'] != 'assumed':
                        continue
                    beklenen = _kural_yeniden(plan, p['id'], ad, d)
                    assert d['value'] == beklenen, (etiket, p['id'], ad)
                    goruldu.add(d['source']['rule'])
                    if ad == 'axial_position_mm' and \
                            p['id'].split('-')[1:] in ([], ['1']):
                        # Konum ölçüsü (ilk) parçanın gerçek ön yüzüdür.
                        assert p['bbox_mm']['x_mm'][0] == d['value']
        assert goruldu >= {'INJECTOR_PLATE_SEAT_RULE',
                           'GRAIN_AXIAL_POSITION_RULE',
                           'NOZZLE_WALL_GENERATOR_RULE'}

    def test_assumed_halka_yaricapi_kural_x_R(self, yanitlar, planlar):
        from hrma.export.step_export import INJECTOR_RING_RADIUS_FRACTIONS as F
        kesirler = set()
        for etiket, plan in _assumed_planlari(yanitlar, planlar):
            kasa = next((p for p in plan['parts']
                         if p['id'] in ('H01', 'L05')), None)
            for p in plan['parts']:
                for i, h in enumerate(p['geometry'].get('holes') or ()):
                    src = h['ring_source']
                    if src['kind'] != 'assumed':
                        continue
                    assert src['rule'] == 'INJECTOR_RING_RADIUS_FRACTIONS'
                    frac = F[min(i, len(F) - 1)]
                    R = kasa['dims']['bore_diameter_mm']['value'] / 2.0
                    assert src['rule_value'] == frac, (etiket, i)
                    assert h['ring_r_mm'] == frac * R, (etiket, i)
                    kesirler.add(frac)
        # İki kesir de en az bir planda sınandı (0,7 R ve 0,38 R).
        assert kesirler == set(F)

    def test_civata_cemberi_cozucu_kurali(self, planlar):
        # defined_at kuralları: sayı çözücünün kendi literal ifadesidir
        # (structural_analysis.py: D/2 + 0,025 m ve D + 0,05 m, metrede
        # hesaplanıp x1000 yayımlanır); plan onu aynen taşır, bekçi
        # ifadeyi planın kendi deliğinden yeniden kurar.
        sayac = 0
        for m in ('hybrid', 'solid', 'liquid'):
            plan = planlar[m]
            kasa = next(p for p in plan['parts']
                        if p['id'] in ('S01', 'H01', 'L05'))
            R = kasa['dims']['bore_diameter_mm']['value'] / 2.0
            for n in plan['not_modelled']:
                yaricap = (n.get('bolt_plan_published') or {}).get(
                    'bolt_circle_radius_mm')
                cap = n.get('end_cap_bolt_circle_diameter_mm')
                for d, kural, ifade in (
                        (yaricap, 'STRUCTURAL_BOLT_CIRCLE_RADIUS_RULE',
                         R + 25.0),
                        (cap, 'STRUCTURAL_BOLT_CIRCLE_DIAMETER_RULE',
                         2.0 * R + 50.0)):
                    if not isinstance(d, dict):
                        continue
                    assert d['source']['kind'] == 'assumed'
                    assert d['source']['rule'] == kural
                    assert d['value'] == d['source']['raw']
                    assert abs(d['value'] - ifade) <= 1e-9, (m, kural)
                    sayac += 1
        assert sayac >= 4


# ---------------------------------------------------------------------------
# Ş5(d) — segment ara boşluğu künyesi (denetçi D11; DV36-05 inceltmesi)
# ---------------------------------------------------------------------------
class TestSegmentBoslukKunyesi:
    def test_ornek_user_input_kullanici(self, planlar):
        for i in (1, 2, 3):
            src = _parca(planlar['solid'], f'S05-{i}')['dims'][
                'segment_gap_mm']['source']
            assert src['kind'] == 'user'
            assert src['solver_code'] == 'user_input'

    @pytest.mark.parametrize('degisiklik, tur', [
        ({'grain_gap_source': 'user_input', 'grain_gap_mm': 0.0}, 'user'),
        ({'grain_gap_source': 'not_supplied_zero', 'grain_gap_mm': 0.0},
         'solver'),
        ({'grain_gap_source': None, 'grain_gap_mm': 2.0}, 'solver'),
        ({'grain_gap_source': None, 'grain_gap_mm': 0.0}, 'not_modelled'),
        ({'grain_gap_mm': None}, 'not_modelled'),
    ])
    def test_kunye_esleme(self, yanitlar, degisiklik, tur):
        g, _inj = _govde(yanitlar, 'solid')
        gd = g['grain_design']
        for k_, v in degisiklik.items():
            if v is None:
                gd.pop(k_, None)
            else:
                gd[k_] = v
        p = build_plan(g, 'solid')
        d = _parca(p, 'S05-2')['dims']['segment_gap_mm']
        assert d['source']['kind'] == tur
        if tur == 'not_modelled':
            # Yayımlanmayan boşluk: segmentler bitişik, sayı uydurulmaz.
            assert d['value'] == 0.0


# ---------------------------------------------------------------------------
# Karar 1 — basınç sınırı kalınlığı ASSUMED çizilmez
# ---------------------------------------------------------------------------
class TestKarar1:
    @pytest.mark.parametrize('m', ['hybrid', 'solid', 'liquid'])
    def test_kalinlik_assumed_degil(self, planlar, m):
        for pid, ad, d in _olculer(planlar[m]):
            if ad in KALINLIK_OLCULERI and d['source']['kind'] == 'assumed':
                assert d['source']['rule'] == 'NOZZLE_WALL_GENERATOR_RULE', \
                    (pid, ad)
                assert pid in ASSUMED_RULES['NOZZLE_WALL_GENERATOR_RULE'][
                    'parts']

    @pytest.mark.parametrize('deger', ['sil', 0.0])
    @pytest.mark.parametrize('m, pid', [('hybrid', 'H02'), ('solid', 'S02'),
                                        ('liquid', 'L16')])
    def test_kapak_alani_yoksa_kapak_yok(self, yanitlar, m, pid, deger):
        # Ş5(b): 0,0 = yayımlanmadı kuralı kapak alanında da (denetçi D7).
        g, inj = _govde(yanitlar, m)
        ec = g['structural_analysis']['end_cap_analysis']
        if deger == 'sil':
            del ec['flat_head_thickness']
        else:
            ec['flat_head_thickness'] = deger
        p = build_plan(g, m, injector=inj)
        assert all(x['id'] != pid for x in p['parts'])
        assert _cizilmeyen(p, pid)['kind'] == 'new_calc_required'

    @pytest.mark.parametrize('deger', ['sil', 0.0])
    def test_astar_kalinligi_sifirsa_astar_yok(self, yanitlar, deger):
        g, inj = _govde(yanitlar, 'hybrid')
        cl = g['thermal_protection']['chamber_liner']
        if deger == 'sil':
            del cl['thickness']
        else:
            cl['thickness'] = deger
        p = build_plan(g, 'hybrid', injector=inj)
        for pid in ('H09a', 'H09b'):
            assert all(x['id'] != pid for x in p['parts'])
            assert _cizilmeyen(p, pid)['kind'] == 'not_modelled'

    def test_plaka_kalinligi_yoksa_plaka_yok(self, yanitlar):
        g, inj = _govde(yanitlar, 'hybrid')
        del g['injector_design']['plate_thickness_mm']
        p = build_plan(g, 'hybrid', injector=inj)
        assert all(x['id'] != 'H03' for x in p['parts'])
        n = _cizilmeyen(p, 'H03')
        assert n['kind'] == 'new_calc_required'
        # Baş payı da kalkar: boru enjektör yüzünden (x = 0) başlar.
        assert _parca(p, 'H01')['bbox_mm']['x_mm'][0] == 0.0

    @pytest.mark.parametrize('pid', ['H11', 'H12', 'H04'])
    def test_hibrit_basinc_parcalari_hesap_bekler(self, planlar, pid):
        assert _cizilmeyen(planlar['hybrid'], pid)['kind'] == \
            'new_calc_required'


# ---------------------------------------------------------------------------
# B5 — girişim / temas / eksenel bütçe
# ---------------------------------------------------------------------------
class TestB5GirisimTemas:
    @pytest.mark.parametrize('m', ['hybrid', 'solid', 'liquid'])
    def test_orneklerde_girisim_yok_temas_dogru(self, planlar, m):
        c = planlar[m]['checks']
        assert c['interference_pairs'] == []
        assert c['contacts_ok'] is True
        for t in planlar[m]['contacts']:
            assert t['ok'] is True, t

    def test_hibrit_eksenel_butce_kapanir(self, planlar):
        b = planlar['hybrid']['checks']['axial_budget']
        assert b['ok'] is True
        assert abs(b['residual_mm']) <= 1e-9
        assert 'reason' not in b

    def test_temas_kirmizi_yolu_birim(self):
        # Ş5(a): beyan ≠ ölçülen temas -> ok False (denetçi D1).
        k = ma._Kurucu('solid')
        k.parca('S01', ma._dikdortgen(0.0, 10.0, 5.0, 6.0), {})
        k.parca('S02', ma._dikdortgen(-3.0, -1.0, 0.0, 6.0), {})
        k.temas('S02', 'S01', 'axial_face', 0.0, 'bekçi: 1 mm açık')
        k.temas('S01', 'S02', 'axial_gap', 1.0, 'bekçi: beyan doğru')
        sonuc = ma._temas_denetimi(k, 1e-3)
        assert sonuc[0]['measured_gap_mm'] == 1.0
        assert sonuc[0]['ok'] is False
        assert sonuc[1]['ok'] is True

    def test_temas_kirmizi_yolu_planda(self, yanitlar, monkeypatch):
        # Gerçek hibrit planında her temas beyanı 1 mm kaydırılır: ölçülen
        # boşluk beyana uymaz -> her temas ok False, contacts_ok False.
        asil = ma._Kurucu.temas

        def kaydir(self, a, b, kind, gap_mm, basis):
            return asil(self, a, b, kind, gap_mm + 1.0, basis)
        monkeypatch.setattr(ma._Kurucu, 'temas', kaydir)
        g, inj = _govde(yanitlar, 'hybrid')
        p = build_plan(g, 'hybrid', injector=inj)
        assert p['contacts']
        assert all(c['ok'] is False for c in p['contacts'])
        assert p['checks']['contacts_ok'] is False

    def test_butce_tane_girisimle_dusunce_maskelenmez(self, yanitlar):
        # Ş4 (denetçi S8): ön oda +0,1 m -> tane lüleyle girişir ve düşer;
        # bütçe yine yayımlanan terimlerden kurulur, artık +100 mm, ok False.
        g, inj = _govde(yanitlar, 'hybrid')
        g['pre_chamber_length'] = g['pre_chamber_length'] + 0.1
        p = build_plan(g, 'hybrid', injector=inj)
        assert all(x['id'] != 'H07' for x in p['parts'])
        assert _cizilmeyen(p, 'H07')['class'] == 'interference'
        b = p['checks']['axial_budget']
        mg = g['motor_geometry']
        beklenen = (g['pre_chamber_length'] * 1000.0
                    + mg['grain_design']['grain_length_mm']
                    + g['post_chamber_length'] * 1000.0
                    - mg['chamber_length'] * 1000.0)
        assert abs(b['residual_mm'] - beklenen) <= 1e-9
        assert abs(b['residual_mm'] - 100.0) <= 1e-6
        assert b['ok'] is False
        assert p['checks']['axial_budget_ok'] is False
        assert b['reason'].startswith(
            'grain not drawn (interference); residual = +100.0000 mm')

    def test_kati_butce_boyut_reddinde_de_kurulur(self, yanitlar):
        # Segment boyu kamarayı taşırırsa tane çizilmez (boyut reddi) ama
        # yığın yayımlanan ölçülerden hesaplanır: 3 x 200 + 2 x 2 = 604.
        g, _inj = _govde(yanitlar, 'solid')
        g['grain_design']['segment_length_mm'] = 200.0
        p = build_plan(g, 'solid')
        assert not any(x['id'].startswith('S05') for x in p['parts'])
        b = p['checks']['axial_budget']
        assert b['stack_mm'] == 604.0
        assert b['ok'] is False
        assert b['reason'].startswith('grain not drawn (rejected: S05)')

    # --- Denetçi-2 ŞB(a): katı yığın eşitliği, beklenen YANIT alanlarından
    @staticmethod
    def _kati_yigin_yanittan(g):
        """Beklenen yığın ve kamara boyu YANIT alanlarından (plan
        ölçülerinden değil): n·segment + (n−1)·boşluk, L = chamber_length."""
        gd = g['grain_design']
        n = int(gd['number_of_segments'])
        yigin = (n * gd['segment_length_mm']
                 + (n - 1) * gd['grain_gap_mm'])
        return yigin, g['chamber_length'] * 1000.0

    @staticmethod
    def _taneye_gomulu_ek(x0, x1, r0, pid='X05'):
        # 'case' rollü (öncelik 100 > itici 70) ek parça, tane iç yüzüne
        # 2 mm gömülü; kapsadığı segment(ler) girişimle düşer, kasa/kapak/
        # lüleye değmez.
        return [{'group': '70_test', 'parts': [{
            'id': pid, 'name': 'probe', 'role': 'case',
            'geometry': {'kind': 'revolve',
                         'profile_rz_mm': [[x0, r0], [x1, r0],
                                           [x1, r0 + 2.0], [x0, r0 + 2.0]]},
            'dims': {}}]}]

    @staticmethod
    def _segmentler(plan):
        return [p for p in plan['parts'] if p['id'].startswith('S05')]

    def test_kati_butce_yigini_yanittan(self, yanitlar, planlar):
        # Örnek: 3 x 120 + 2 x 2 = 364 mm (ölçüm çapası); stack_mm ve
        # free_mm yanıttan bağımsız hesapla aynı (denetçi-2 E8/E9).
        g, _inj = _govde(yanitlar, 'solid')
        yigin, L = self._kati_yigin_yanittan(g)
        assert yigin == 364.0
        b = planlar['solid']['checks']['axial_budget']
        assert b['stack_mm'] == yigin
        assert abs(b['chamber_length_mm'] - L) <= 1e-9
        assert abs(b['free_mm'] - (L - yigin)) <= 1e-9
        assert b['ok'] is True
        assert 'reason' not in b

    def test_kati_butce_butun_segmentler_dusunce(self, yanitlar, planlar):
        # Bütün segmentler girişimle düşer: yığın yine yayımlanan segment
        # ölçülerinden, aynı eşitlik; ok True (yığın L'ye sığıyor).
        seg = self._segmentler(planlar['solid'])
        assert len(seg) == 3
        x0 = min(p['bbox_mm']['x_mm'][0] for p in seg)
        x1 = max(p['bbox_mm']['x_mm'][1] for p in seg)
        r0 = seg[0]['bbox_mm']['r_mm'][0]
        g, _inj = _govde(yanitlar, 'solid')
        p = build_plan(g, 'solid', extra_groups=self._taneye_gomulu_ek(
            x0, x1, r0))
        assert self._segmentler(p) == []
        assert [n['id'] for n in p['not_modelled']
                if n.get('class') == 'interference'] == [
            'S05-1', 'S05-2', 'S05-3']
        b = p['checks']['axial_budget']
        yigin, L = self._kati_yigin_yanittan(g)
        assert b['stack_mm'] == yigin
        assert abs(b['free_mm'] - (L - yigin)) <= 1e-9
        assert b['ok'] is True
        assert b['reason'] == (f'grain not drawn (interference); '
                               f'free = {L - yigin:+.4f} mm')

    def test_kati_butce_kismi_dusus_kimlikleri(self, yanitlar, planlar):
        # Yalnız S05-2 düşer: gerekçe düşen ve çizilen kimlikleri ADIYLA
        # yazar ("tane çizilmedi" denip S05-1/S05-3 gizlenmez).
        s2 = next(p for p in self._segmentler(planlar['solid'])
                  if p['id'] == 'S05-2')
        x0, x1 = s2['bbox_mm']['x_mm']
        g, _inj = _govde(yanitlar, 'solid')
        p = build_plan(g, 'solid', extra_groups=self._taneye_gomulu_ek(
            x0 + 10.0, x1 - 10.0, s2['bbox_mm']['r_mm'][0]))
        assert [x['id'] for x in self._segmentler(p)] == ['S05-1', 'S05-3']
        assert _cizilmeyen(p, 'S05-2')['class'] == 'interference'
        b = p['checks']['axial_budget']
        yigin, L = self._kati_yigin_yanittan(g)
        assert b['stack_mm'] == yigin
        assert b['ok'] is True
        assert b['reason'] == ('grain partly not drawn: S05-2 '
                               '(interference); drawn: S05-1, S05-3; '
                               f'free = {L - yigin:+.4f} mm')

    # --- Denetçi-2 ŞB(b): YALNIZ BİR temas beyanı kayar (E11: all -> any)
    @pytest.mark.parametrize('m, cift', [
        ('hybrid', ('H02', 'H03', 'axial_gap')),
        ('solid', ('S05-1', 'S05-2', 'axial_gap'))])
    def test_temas_tek_beyan_kayar(self, yanitlar, monkeypatch, m, cift):
        asil = ma._Kurucu.temas

        def kaydir(self, a, b, kind, gap_mm, basis):
            if (a, b, kind) == cift:
                gap_mm = gap_mm + 1.0
            return asil(self, a, b, kind, gap_mm, basis)
        monkeypatch.setattr(ma._Kurucu, 'temas', kaydir)
        g, inj = _govde(yanitlar, m)
        p = build_plan(g, m, injector=inj)
        hedef = [c for c in p['contacts']
                 if (c['a'], c['b'], c['kind']) == cift]
        oteki = [c for c in p['contacts']
                 if (c['a'], c['b'], c['kind']) != cift]
        assert len(hedef) == 1
        assert hedef[0]['ok'] is False
        assert abs(hedef[0]['gap_mm'] - hedef[0]['measured_gap_mm']
                   - 1.0) <= 1e-9
        assert len(oteki) >= 2
        assert all(c['ok'] is True for c in oteki)
        assert p['checks']['contacts_ok'] is False

    def test_delik_denetimi_sinir_birim(self):
        # Ş5(e): plaka dış yarıçapı 10 mm, Ø2 delik. Halka 9 -> kenar tam
        # 10 (içeride), halka 9,5 -> kenar 10,5 (DIŞARIDA) (denetçi D9).
        k = ma._Kurucu('hybrid')
        delik = {'circuit': 'oxidizer', 'n': 4, 'd_mm': 2.0}
        k.parca('H03', ma._dikdortgen(-3.0, 0.0, 0.0, 10.0), {},
                holes=[dict(delik, ring_r_mm=9.0),
                       dict(delik, circuit='fuel', ring_r_mm=9.5, n=40)])
        ic, dis = ma._delik_denetimi(k)
        assert ic['inside_plate'] is True
        assert dis['inside_plate'] is False
        # Adım: 2π·9/4 = 14,1 > 2 (örtüşmez); 2π·9,5/40 = 1,49 < 2 (örtüşür).
        assert ic['holes_do_not_overlap'] is True
        assert dis['holes_do_not_overlap'] is False

    def test_delik_plaka_disina_tasarsa_planda(self, yanitlar, planlar):
        from hrma.export.step_export import resolve_injector_circuits
        assert planlar['hybrid']['checks']['holes'][0]['inside_plate'] is True
        g, inj = _govde(yanitlar, 'hybrid')
        g.setdefault('injector', inj)
        blok, _ad, devreler, _e = resolve_injector_circuits(
            g, motor_type='hybrid')
        rc = _parca(planlar['hybrid'], 'H01')['dims']['bore_diameter_mm'][
            'value'] / 2.0
        d = devreler[0]['d_mm']
        # Halka yarıçapı çözücü alanı olarak yayımlanır: delik kenarı
        # plakanın dış yarıçapını d/4 aşar.
        blok['orifice_ring_radius_mm'] = rc - d / 4.0
        p = build_plan(g, 'hybrid', injector=inj)
        h = p['checks']['holes'][0]
        assert _parca(p, 'H03')['geometry']['holes'][0]['ring_source'][
            'kind'] == 'solver'
        assert h['inside_plate'] is False

    def test_girisen_parca_cizilmez_dosya_uretilir(self, planlar, yanitlar):
        # Plakayla 1 mm eksenel örtüşen bir ek parça: plaka (öncelik 80)
        # kalır, ek parça (conta, 40) düşer; hata YOK.
        # Uyum turu (14 Eki): sonda eskiden [-1, 5] mm'deydi (plaka
        # [-t, 0]'dayken arka yüzünü 1 mm örten konum). CAD H8 plakayı kapak
        # iç yüzüne oturttu; sonda aynı ilişkiyle plakanın arka yüzüne
        # konur: x1 = oturma yeri (CAD sabiti) + yanıttaki plaka kalınlığı.
        from hrma.export.cad_visualization import INJECTOR_PLATE_SEAT_X_MM
        g, inj = _govde(yanitlar, 'hybrid')
        x1 = INJECTOR_PLATE_SEAT_X_MM + g['injector_design'][
            'plate_thickness_mm']
        ek = [{'group': '70_test', 'parts': [{
            'id': 'X01', 'name': 'probe', 'role': 'seal',
            'geometry': {'kind': 'revolve',
                         'profile_rz_mm': [[x1 - 1.0, 10.0], [x1 + 5.0, 10.0],
                                           [x1 + 5.0, 20.0],
                                           [x1 - 1.0, 20.0]]},
            'dims': {}}]}]
        p = build_plan(g, 'hybrid', injector=inj, extra_groups=ek)
        assert any(x['id'] == 'H03' for x in p['parts'])
        assert all(x['id'] != 'X01' for x in p['parts'])
        cift = [c for c in p['checks']['interference_pairs']
                if {'X01', 'H03'} == {c['a'], c['b']}]
        assert cift and cift[0]['not_drawn'] == ['X01']
        assert abs(cift[0]['penetration_mm'] - 1.0) < 0.2
        assert _cizilmeyen(p, 'X01')['class'] == 'interference'

    def test_esit_oncelikte_ikisi_de_dusmez_kalmaz(self, yanitlar):
        # Ölçülen vaka (K-6): astar + yalıtım yığını tane-kasa boşluğundan
        # 2,0 mm kalın -> eşit öncelikli iki ısıl katman da çizilmez.
        # V301/T-ÇAPA-D: K-A kasa kapısı (1b71ef5a3) kasayı artık tane +
        # 2·(astar + yalıtım) alacak kadar geniş kuruyor (sığmayan beyan 422);
        # gerçek katı yanıtında girişim OLUŞMUYOR. Vaka aynı örtüşmeyle
        # kurulur: yanıtın ısıl bariyer bloğunda astar 2,0 mm kalınlaştırılır
        # (kasa ve tane yanıtın kendi sayıları).
        g = copy.deepcopy(yanitlar['solid'])
        tb = None
        for yol in (('cad_design', 'insulation_system', 'thermal_barrier'),
                    ('insulation_system', 'thermal_barrier')):
            d = g
            for parca in yol:
                d = d.get(parca) if isinstance(d, dict) else None
            if isinstance(d, dict):
                tb = d
                break
        assert tb is not None and tb.get('liner_thickness'), (
            'ön koşul: yanıt ısıl bariyer bloğunu (astar kalınlığı) taşımalı')
        tb['liner_thickness'] = float(tb['liner_thickness']) + 2.0
        p = build_plan(g, 'solid')
        dusen = {n['id'] for n in p['not_modelled']
                 if n.get('class') == 'interference'}
        assert dusen == {'S06', 'S07'}
        cift = p['checks']['interference_pairs'][0]
        assert abs((cift['overlap_r_mm'][1] - cift['overlap_r_mm'][0])
                   - 2.0) < 1e-9


class TestSafGeometri:
    def test_dikdortgen_ortusme(self):
        a = [[0, 0], [4, 0], [4, 2], [0, 2]]
        b = [[3, 1], [6, 1], [6, 5], [3, 5]]
        o = section_overlap(a, b)
        assert abs(o['area_mm2'] - 1.0) < 1e-12
        assert o['x_mm'] == [3.0, 4.0] and o['r_mm'] == [1.0, 2.0]

    def test_degme_ortusme_degil(self):
        a = [[0, 0], [4, 0], [4, 2], [0, 2]]
        b = [[4, 0], [6, 0], [6, 2], [4, 2]]
        assert section_overlap(a, b)['area_mm2'] == 0.0
        assert section_distance(a, b) == 0.0

    def test_uzaklik(self):
        a = [[0, 0], [1, 0], [1, 1], [0, 1]]
        b = [[3, 0], [4, 0], [4, 1], [3, 1]]
        assert section_distance(a, b) == 2.0

    def test_icbukey_profil(self):
        # L biçimli kesit ile köşedeki kare: örtüşme yalnız L'nin kolunda.
        L = [[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]]
        kare = [[2, 2], [3, 2], [3, 3], [2, 3]]
        assert section_overlap(L, kare)['area_mm2'] == 0.0
        kare2 = [[0.5, 0.5], [2, 0.5], [2, 2], [0.5, 2]]
        # Kesişim: [0.5,2]x[0.5,1] (1,5 x 0,5) + [0.5,1]x[1,2] (0,5 x 1)
        assert abs(section_overlap(L, kare2)['area_mm2'] - 1.25) < 1e-12

    def test_pappus_hacmi(self):
        assert abs(profile_volume_mm3([[0, 1], [2, 1], [2, 3], [0, 3]])
                   - math.pi * (9 - 1) * 2) < 1e-12
        # Koni kesiti (üçgen x∈[0,h], r∈[0,R]): V = π R² h / 3
        R, h = 2.0, 3.0
        assert abs(profile_volume_mm3([[0, 0], [h, 0], [0, R]])
                   - math.pi * R * R * h / 3) < 1e-12


# ---------------------------------------------------------------------------
# İmza, cıvata künyesi, ablatif ölçüm, ekleme noktası, motor tipi
# ---------------------------------------------------------------------------
class TestImza:
    def test_imza_tanimi(self, planlar):
        p = planlar['hybrid']
        beklenen = hashlib.sha256(
            canonical_json(p['parts']).encode('utf-8')).hexdigest()[:16]
        assert p['plan_signature'] == beklenen == plan_signature(p['parts'])

    def test_imza_kararli_ve_duyarli(self, yanitlar, planlar):
        g, inj = _govde(yanitlar, 'solid')
        assert build_plan(g, 'solid')['plan_signature'] == \
            planlar['solid']['plan_signature']
        g2 = copy.deepcopy(g)
        g2['structural_analysis']['case_analysis']['wall_thickness_mm'] += \
            1e-9
        assert build_plan(g2, 'solid')['plan_signature'] != \
            planlar['solid']['plan_signature']


class TestCivataKunyesi:
    def test_sahne_ile_bayt_ayni(self):
        js = (KOK / 'hrma/static/js/motor_viz3d.js').read_text(
            encoding='utf-8')
        metin = ASSUMED_RULES['STRUCTURAL_BOLT_CIRCLE_RADIUS_RULE']['text']
        assert f"var BOLT_CIRCLE_BASIS = '{metin}';" in js

    def test_kural_cozucunun_kendi_sayisiyla(self, planlar):
        # Künyedeki "+25 mm" / "+50 mm" iddiası çözücünün yayımladığı
        # sayılardan ölçülür (bekçi kuralı kopyalamaz, ölçer).
        e = _cizilmeyen(planlar['hybrid'], 'H14')
        assert abs(e['bolt_plan_published']
                   ['bolt_circle_offset_from_bore_mm'] - 25.0) < 1e-9
        assert e['bolt_plan_published']['bolt_circle_radius_mm']['source'][
            'kind'] == 'assumed'
        for m, pid in (('hybrid', 'H14'), ('solid', 'S14'),
                       ('liquid', 'L15')):
            e = _cizilmeyen(planlar[m], pid)
            assert abs(e['end_cap_bolt_circle_offset_from_bore_mm']
                       - 50.0) < 1e-9
            assert e['end_cap_bolt_circle_diameter_mm']['source']['rule'] == \
                'STRUCTURAL_BOLT_CIRCLE_DIAMETER_RULE'

    @pytest.mark.parametrize('m', ['hybrid', 'solid', 'liquid'])
    def test_civata_cizilmez(self, planlar, m):
        assert not any(p['role'] == 'fastener' for p in planlar[m]['parts'])


class TestAblatifNedeni:
    """Ş1 (denetçi): kapak yalıtımı gerekçesi ÇÖZÜCÜNÜN KENDİ metninden;
    NO NET HEATING ve F-CAD-11 yeniden tanımı yalnız çözücü öyle diyorsa."""

    ANAHTAR = {'S08a': 'forward_insulation', 'S08b': 'aft_insulation'}
    BASKA = ('Ablative sizing at the forward closure needs the gas-side '
             'station inputs of this run and could not get them: the Bartz '
             'gas-side chain could not be evaluated. No number is invented.')

    def _blok(self, g, pid):
        return g['cad_design']['insulation_system'][self.ANAHTAR[pid]]

    @pytest.mark.parametrize('pid', ['S08a', 'S08b'])
    def test_cozucu_metni_aynen_nnh(self, yanitlar, pid):
        g = copy.deepcopy(yanitlar['solid'])
        blok = self._blok(g, pid)
        # Ön koşul (ölçüm): bugünkü çözücü NO NET HEATING diyor.
        assert 'NO NET HEATING' in blok['basis']
        n = _cizilmeyen(build_plan(g, 'solid'), pid)
        assert blok['basis'] in n['reason']
        assert n['solver_basis_field'] == (
            f'cad_design.insulation_system.{self.ANAHTAR[pid]}.basis')
        assert n['solver_no_net_heating'] is True
        assert n['replaced_by'] == ma.FCAD11_TRANSIENT_REDEFINITION

    @pytest.mark.parametrize('validity', ['koru', 'sil'])
    @pytest.mark.parametrize('pid', ['S08a', 'S08b'])
    def test_baska_neden_nnh_iddia_etmez(self, yanitlar, pid, validity):
        # Çözücünün gerekçesi başka bir nedene dönünce plan NO NET HEATING
        # İDDİA ETMEZ ve çözücünün yeni metnini taşır. 'sil' = çözücünün
        # Q* koşulamayan dalının biçimi (yalnız basis yayımlanır).
        g = copy.deepcopy(yanitlar['solid'])
        blok = self._blok(g, pid)
        blok['basis'] = self.BASKA
        if validity == 'sil':
            blok.pop('validity_note', None)
        n = _cizilmeyen(build_plan(g, 'solid'), pid)
        assert 'NO NET HEATING' not in n['reason']
        assert self.BASKA in n['reason']
        assert n['replaced_by'] == 'F-CAD-11'
        assert n['solver_no_net_heating'] is False

    def test_basis_yoksa_validity_note(self, yanitlar):
        g = copy.deepcopy(yanitlar['solid'])
        blok = self._blok(g, 'S08a')
        not_ = blok['validity_note']
        blok.pop('basis')
        n = _cizilmeyen(build_plan(g, 'solid'), 'S08a')
        assert not_ in n['reason']
        assert n['solver_basis_field'].endswith('.validity_note')
        assert n['replaced_by'] == ma.FCAD11_TRANSIENT_REDEFINITION

    def test_metin_yoksa_basis_not_published(self, yanitlar):
        g = copy.deepcopy(yanitlar['solid'])
        blok = self._blok(g, 'S08a')
        blok.pop('basis')
        blok.pop('validity_note', None)
        n = _cizilmeyen(build_plan(g, 'solid'), 'S08a')
        assert 'basis not published' in n['reason']
        assert 'NO NET HEATING' not in n['reason']
        assert n['replaced_by'] == 'F-CAD-11'
        assert n['solver_basis_field'] is None

    def test_kok_insulation_system_kunye_yolu(self, yanitlar):
        # Düz gövde kökü (INSULATION_BLOCK_ROOTS[1]): künye yolu bloğun
        # BULUNDUĞU kökü gösterir (denetçi-2 E3).
        g = copy.deepcopy(yanitlar['solid'])
        assert 'insulation_system' not in g
        g['insulation_system'] = g['cad_design'].pop('insulation_system')
        n = _cizilmeyen(build_plan(g, 'solid'), 'S08a')
        assert n['solver_basis_field'] == (
            'insulation_system.forward_insulation.basis')
        assert g['insulation_system']['forward_insulation']['basis'] in \
            n['reason']
        assert n['solver_no_net_heating'] is True

    def test_ihrac_govdesinde_blok_yok(self, planlar):
        for pid in ('S08a', 'S08b'):
            n = _cizilmeyen(planlar['solid'], pid)
            assert 'NO NET HEATING' not in n['reason']
            assert 'no ' + self.ANAHTAR[pid] + ' block' in n['reason']
            assert n['replaced_by'] == 'F-CAD-11'

    def test_kati_ihrac_govdesi_isil_bariyer_tasimaz(self, planlar):
        for pid in ('S06', 'S07'):
            assert 'does not carry' in _cizilmeyen(planlar['solid'],
                                                   pid)['reason']


class TestEkGruplar:
    def _parca(self, pid='T01', grup='70_turbo'):
        return {'group': grup, 'parts': [{
            'id': pid, 'name': 'pump_casing_envelope', 'role': 'feed',
            'geometry': {'kind': 'revolve',
                         'profile_rz_mm': [[2000, 0], [2100, 0], [2100, 50],
                                           [2000, 50]]},
            'dims': {'length_mm': {'value': 100.0, 'source': {
                'kind': 'assumed', 'rule': 'TEST'}}}}]}

    def test_gecerli_ek_grup(self, yanitlar, planlar):
        g, inj = _govde(yanitlar, 'liquid')
        p = build_plan(g, 'liquid', extra_groups=[self._parca()])
        assert _parca(p, 'T01')['group'] == '70_turbo'
        assert p['plan_signature'] != planlar['liquid']['plan_signature']
        assert p['inputs']['extra_parts'] == ['T01']

    @pytest.mark.parametrize('bozuk', [
        {'grup': '10_case'}, {'grup': 'turbo'}, {'pid': 'L05'}])
    def test_gecersiz_ek_grup(self, yanitlar, bozuk):
        g, _inj = _govde(yanitlar, 'liquid')
        e = self._parca(pid=bozuk.get('pid', 'T01'),
                        grup=bozuk.get('grup', '70_turbo'))
        with pytest.raises(AssemblyPlanError):
            build_plan(g, 'liquid', extra_groups=[e])


class TestMotorTipiVeCapa:
    @pytest.mark.parametrize('tip', [None, 'rocket', 7])
    def test_tanimsiz_tip(self, tip):
        with pytest.raises(AssemblyPlanError):
            build_plan({}, tip)

    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    def test_capasiz_plan_ek_parca_cizilmez(self, tip):
        # Ş3 (denetçi S2): çapasız planda ek grup parçası da ÇİZİLMEZ.
        ek = [{'group': '70_turbo', 'parts': [{
            'id': 'T01', 'name': 'probe', 'role': 'feed',
            'geometry': {'kind': 'revolve',
                         'profile_rz_mm': [[0, 0], [10, 0], [10, 5],
                                           [0, 5]]},
            'dims': {}}]}]
        p = build_plan({}, tip, extra_groups=ek)
        assert p['status'] == 'not_drawable'
        assert p['parts'] == []
        n = _cizilmeyen(p, 'T01')
        assert n['kind'] == 'not_modelled'
        assert n['class'] == 'not_anchored'
        assert n['reason'].startswith('plan not anchored')
        assert p['inputs']['extra_parts'] == ['T01']
        assert p['checks']['interference_pairs'] == []

    def test_capasiz_plan_hicbir_sey_cizmez(self):
        p = build_plan({'motor_name': 'x'}, 'solid')
        assert p['status'] == 'not_drawable'
        assert p['parts'] == []
        assert {n['id'] for n in p['not_modelled']} == \
            {k[0] for k in PART_CATALOG['solid']}
        assert {f['field'] for f in p['invalid_fields']} >= \
            {'chamber_length', 'chamber_diameter'}


class TestHacimIkinciYol:
    """Plan profilinin Pappus hacmi ⟷ bugünkü STEP'in OCC hacmi (aynı
    geometriyi anlatan parçalarda; katı ve sıvı ihraç gövdesi)."""

    @pytest.mark.parametrize('m', ['solid', 'liquid'])
    def test_step_occ_hacmiyle_ayni(self, yanitlar, planlar, m, tmp_path):
        pytest.importorskip('build123d')
        from build123d import import_step
        from hrma.export.step_export import generate_step_assembly
        g, _inj = _govde(yanitlar, m)
        yollar = generate_step_assembly(g, out_dir=str(tmp_path),
                                        motor_type=m)
        occ = {ad: sum(s.volume for s in import_step(y).solids())
               for ad, y in yollar.items() if ad != 'assembly'}
        p = planlar[m]
        kasa = {'solid': ('S01', 'S02'), 'liquid': ('L05', 'L16')}[m]
        lule = {'solid': 'S09', 'liquid': 'L10'}[m]
        plan_kamara = sum(part_volume_mm3(_parca(p, x)) for x in kasa)
        assert abs(plan_kamara - occ['chamber']) / occ['chamber'] < 1e-6
        # Lüle (ana model çevirisi, 14 Eki; dört koşul): CAD pürüzsüz yüzey
        # turu (karar §28-41) STEP lülesini AYNI kontur noktalarından geçen
        # dönel B-spline yaptı; eski beklenti ('STEP = aynı noktaların
        # doğrusal parçaları') o temsilden türemişti. İkinci yol artık planın
        # kendi çokgeninin OCC dönel katısı (Pappus ⟷ OCC, aynı geometri,
        # tolerans AYNI). Plan ⟷ STEP bağı tek kontur kaynağıdır
        # (sample_nozzle_inner_contour); B-spline'ın bu noktalardan geçtiğini
        # CAD kulvarının bekçisi ölçer (test_v3_cad_duzeltme TestPuruzsuzYuzey).
        from build123d import Axis, Polyline, make_face, revolve
        cokgen = [tuple(q) for q in
                  _parca(p, lule)['geometry']['profile_rz_mm']]
        if cokgen[0] == cokgen[-1]:
            cokgen = cokgen[:-1]
        occ_cokgen = revolve(make_face(Polyline(*cokgen, close=True)),
                             Axis.X).volume
        assert abs(part_volume_mm3(_parca(p, lule)) - occ_cokgen) \
            / occ_cokgen < 1e-6
        if m == 'solid':
            tane = sum(part_volume_mm3(x) for x in p['parts']
                       if x['id'].startswith('S05'))
            assert abs(tane - occ['fuel_grain']) / occ['fuel_grain'] < 1e-6


class TestPlakaCadTekKaynak:
    """Uyum turu (14 Eki): plakanın eksenel yeri CAD kulvarının TEK
    kuralından (``cad_visualization.injector_plate_axial_span_mm``, ÖH V3
    CAD A1 · H8, karar §28-21). Plan ikinci bir yerleşim yazmaz: oturma
    yeri değişirse plan da onu izler (kâhin = CAD fonksiyonunun kendisi)."""

    def test_plaka_yeri_cad_tek_kaynagindan(self, yanitlar, monkeypatch):
        from hrma.export import cad_visualization as cv
        # Oturma yeri sondası: 2,0 mm (yalnız bu testte; ürün değeri 0).
        monkeypatch.setattr(cv, 'INJECTOR_PLATE_SEAT_X_MM', 2.0)
        g, inj = _govde(yanitlar, 'hybrid')
        t = g['injector_design']['plate_thickness_mm']
        x0, x1, not_ = cv.injector_plate_axial_span_mm(t)
        assert (x0, x1) == (2.0, 2.0 + t)
        p = build_plan(g, 'hybrid', injector=inj)
        plaka = _parca(p, 'H03')
        assert plaka['bbox_mm']['x_mm'] == [x0, x1]
        assert plaka['dims']['axial_position_mm']['value'] == x0
        assert plaka['dims']['axial_position_mm']['source'] == {
            'kind': 'assumed', 'rule': 'INJECTOR_PLATE_SEAT_RULE',
            'basis': not_}
        assert not_ in plaka['declared']
        temas = [c for c in p['contacts']
                 if (c['a'], c['b']) == ('H02', 'H03')]
        assert len(temas) == 1
        assert temas[0]['gap_mm'] == x0 and temas[0]['ok'] is True
        # Ön oda astarı plakanın arka yüzünden başlar (girişim yok).
        assert _parca(p, 'H09a')['bbox_mm']['x_mm'][0] == x1
        assert p['checks']['contacts_ok'] is True

    def test_ornek_planda_plaka_kapak_ic_yuzunde(self, planlar, yanitlar):
        from hrma.export.cad_visualization import INJECTOR_PLATE_SEAT_X_MM
        g, _inj = _govde(yanitlar, 'hybrid')
        t = g['injector_design']['plate_thickness_mm']
        p = planlar['hybrid']
        assert _parca(p, 'H03')['bbox_mm']['x_mm'] == [
            INJECTOR_PLATE_SEAT_X_MM, INJECTOR_PLATE_SEAT_X_MM + t]
        # Boru öne uzamaz (eski head_allowance_mm kalktı), kapak x <= 0.
        kasa = _parca(p, 'H01')
        assert 'head_allowance_mm' not in kasa['dims']
        assert kasa['bbox_mm']['x_mm'][0] == 0.0
        assert _parca(p, 'H02')['bbox_mm']['x_mm'][1] == 0.0

    def test_plaka_kamaraya_sigmazsa_cizilmez(self, yanitlar, planlar):
        g, inj = _govde(yanitlar, 'hybrid')
        L = _parca(planlar['hybrid'], 'H01')['dims']['chamber_length_mm'][
            'value']
        g['injector_design']['plate_thickness_mm'] = L + 1.0
        p = build_plan(g, 'hybrid', injector=inj)
        assert all(x['id'] != 'H03' for x in p['parts'])
        n = _cizilmeyen(p, 'H03')
        assert 'shorter_than_injector_plate' in n['reason']
        assert n['dims']['thickness_mm']['value'] == L + 1.0
        assert 'no injector plate is placed' in _cizilmeyen(p, 'H04')[
            'reason']
