"""POST /api/fea/structural bekçileri (D5 — yapısal FEA kullanıcı yüzü).

KAPATILAN KUSUR
---------------
``hrma/fea/`` çözücüleri (mesh_axisym + structural_axisym + bridge) depoda
çalışır hâldeydi ama HİÇBİR uç noktası onları çağırmıyordu: kullanıcı ne
gerilme alanını ne mesh'i ne de yakınsama geçmişini görebiliyordu. Bu uç
köprüyü koşturur ve ÇİZİLEBİLİR ham veriyi döner.

NE KİLİTLENİR
-------------
  1. GERÇEK koşu: motor sonucundan uçtan uca FEA → HTTP 200, ``status='ok'``,
     düğüm alanları düğüm sayısıyla aynı uzunlukta, emniyet katsayısı her
     düğümde POZİTİF, von Mises sonlu.
  2. SADAKAT: emniyet katsayısı alanı gerçekten ``akma / von Mises``tir
     (uç, çözücünün alanını yeniden ölçekleyemez); mesh ızgarası beyan
     edilen düğüm sayısıyla tutarlıdır.
  3. EKSİK GİRDİ = RED: köprünün NOT_MODELLED gövdesi 200 ile AYNEN geçer,
     ``missing`` eksiği adlandırır ve gövdede HİÇBİR çözüm alanı bulunmaz
     (sahte veri yasağı).
  4. ÇÖZÜCÜ HATASI = 500: mesh üretilemeyen geometride "boş ama başarılı"
     yanıt üretilmez.
  5. KALİTE ÖLÇÜTLERİ: en-boy oranı >= 1, ölçekli Jacobian (0, 1] aralığında,
     eşikler yanıtta SAYI olarak gelir (panelin tek eşik kaynağı budur) ve
     sayımlar dizilerle tutarlıdır.
  6. UZUN KOŞU SINIRI: eleman sayısı üst sınırı aşılmaz; sınır uygulandıysa
     bu ``limits.clamped`` ile BEYAN edilir (sessiz mesh bozma yok).

ÖLÇÜM YÖNTEMİ
-------------
Sunucuya port BAĞLANMAZ; Flask ``test_client`` kullanılır. İki girdi yolu
sınanır: (a) GERÇEK ``/calculate`` hibrit sonucu, (b) motor sonucu
biçiminde kurulmuş ama alanları GERÇEK kaynaklardan gelen sentetik sözlük
(kontur ``hrma.engines.nozzle_design.sample_nozzle_inner_contour``
örnekleyicisinden, malzeme ``hrma.data.materials_db`` kaydından). (b)
FEA sayılarını uydurmaz — çözücü gerçekten koşar; yalnız motor koşusunun
kendisi atlanır, böylece bu bekçi motor çözücüsünün o günkü durumuna
bağımlı olmaz.

Bekçi kusuru KİLİTLEMEZ: hiçbir gerilme/SF/eleman sayısı sabit sayıya
bağlanmamıştır; kilitlenen şey sözleşme ve tutarlılıktır.
"""

import contextlib
import io
import warnings

import numpy as np
import pytest

warnings.filterwarnings('ignore')

FEA_ENDPOINT = '/api/fea/structural'

# Küçük-mesh koşu parametreleri — bekçinin işi sayısal hassasiyet değil
# (o tests/fea/test_yapisal_dogrulama.py'nin işi), zincirin sadakati.
KUCUK_KOSU = {'n_axial0': 12, 'n_radial0': 4, 'max_rounds': 2}

# Redli (NOT_MODELLED) gövdede BULUNMAMASI zorunlu çözüm alanları.
FEA_REDDE_BULUNMAYACAK_ALANLAR = ('mesh', 'fields', 'quality', 'scalars', 'convergence')


def _quiet(fn, *args, **kwargs):
    """Motor/çözücü modülleri stdout'a bolca basıyor; testte sessize al."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def gercek_kontur_noktalari():
    """GERÇEK lüle kontur örnekleyicisinden [z_m, r_m] noktaları.

    Motorların yayımladığı ``nozzle_contour.points`` ile aynı üreticidir
    (hrma.engines.nozzle_design.sample_nozzle_inner_contour, mm döner);
    burada yalnız metreye çevrilir — kontur UYDURULMAZ.
    """
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    pts, _meta = _quiet(sample_nozzle_inner_contour, {
        'chamber_diameter': 0.10,
        'throat_diameter': 0.030,
        'exit_diameter': 0.075,
        'nozzle_angles': {'nozzle_type': 'conical',
                          'convergent_half_angle_deg': 30,
                          'divergent_half_angle_deg': 15},
    })
    return [[z / 1000.0, r / 1000.0] for z, r in pts]


def sentetik_hibrit_motor(**degisiklik):
    """Hibrit sonuç BİÇİMİNDE, alanları gerçek kaynaklardan gelen sözlük.

    Köprünün hibrit alan haritasıyla (bkz. hrma/fea/bridge.py modül
    docstring'i) birebir aynı anahtarları taşır: kontur, cidar kalınlığı,
    malzeme anahtarı (materials_db kaydı) ve kamara basıncı. FEA sonucu bu
    girdilerden GERÇEKTEN hesaplanır.
    """
    motor = {
        'chamber_pressure': 30.0,          # bar (üst düzey alan bar taşır)
        'chamber_length': 0.35,            # m (hibrit self.L)
        'nozzle_contour': {'points': gercek_kontur_noktalari()},
        'structural_analysis': {
            'chamber_analysis': {'wall_thickness_used_mm': 3.0,
                                 'design_mode': 'verify'},
            'design_parameters': {'material': 'ss_304'},
            'material_properties': {'yield_strength': 215e6},
        },
    }
    motor.update(degisiklik)
    return motor


def kos(client, motor, **ek):
    """Ucu çağırır; (http_kodu, gövde) döner."""
    yuk = dict(KUCUK_KOSU)
    yuk.update(ek)
    yuk['motor_results'] = motor
    resp = _quiet(client.post, FEA_ENDPOINT, json=yuk)
    return resp.status_code, resp.get_json()


@pytest.fixture(scope='module')
def sentetik_sonuc(client):
    kod, govde = kos(client, sentetik_hibrit_motor())
    assert kod == 200, govde
    assert govde['status'] == 'success'
    fea = govde['fea']
    assert fea['status'] == 'ok', fea
    return fea


# ---------------------------------------------------------------------------
# 1. GERÇEK motor koşusu — /calculate sonucu doğrudan uca verilir
# ---------------------------------------------------------------------------
class TestGercekMotor:
    @pytest.fixture(scope='class')
    def hibrit_motor(self, client):
        yuk = {'motor_name': 'fea-ui', 'fuel_type': 'htpb',
               'oxidizer_type': 'n2o', 'thrust': 2000, 'burn_time': 10,
               'chamber_pressure': 30, 'of_ratio': 6.0}
        resp = _quiet(client.post, '/calculate', json=yuk)
        if resp.status_code != 200:
            pytest.skip('/calculate hibrit hesabı bu derlemede koşmuyor '
                        '(FEA ucunun kusuru değil): '
                        + resp.get_data(as_text=True)[:200])
        motor = resp.get_json().get('motor')
        if not isinstance(motor, dict):
            pytest.skip("/calculate yanıtında 'motor' bloğu yok")
        return motor

    def test_gercek_hibrit_sonucu_200_ve_alanlar(self, client, hibrit_motor):
        kod, govde = kos(client, hibrit_motor)
        assert kod == 200, govde
        fea = govde['fea']
        if fea['status'] != 'ok':
            # Motor konturu/yapısal bloğu yayımlamıyorsa red DÜRÜSTTÜR;
            # ama o zaman gövdede çözüm alanı da bulunmamalıdır.
            assert fea['missing'], fea
            for alan in FEA_REDDE_BULUNMAYACAK_ALANLAR:
                assert alan not in fea or alan == 'limits'
            pytest.skip('gerçek motor sonucu FEA girdilerini yayımlamamış: '
                        + str(fea.get('missing')))
        assert fea['engine_layout'] == 'hybrid'
        assert len(fea['fields']['von_mises_pa']) == fea['mesh']['n_nodes']
        assert all(v is not None and np.isfinite(v)
                   for v in fea['fields']['von_mises_pa'])

    def test_gercek_kosuda_sf_alani_pozitif(self, client, hibrit_motor):
        kod, govde = kos(client, hibrit_motor)
        fea = govde['fea']
        if fea['status'] != 'ok' or fea['fields']['safety_factor'] is None:
            pytest.skip('bu motor sonucunda SF alanı yayımlanmıyor')
        assert min(fea['fields']['safety_factor']) > 0.0


# ---------------------------------------------------------------------------
# 2. Sözleşme — sentetik (ama gerçek kaynaklı) girdiyle tam koşu
# ---------------------------------------------------------------------------
class TestSozlesme:
    def test_mesh_dugum_sayisi_izgarayla_tutarli(self, sentetik_sonuc):
        mesh = sentetik_sonuc['mesh']
        izgara = mesh['node_index_grid']
        assert len(izgara) == mesh['n_axial'] + 1
        assert len(izgara[0]) == mesh['n_radial'] + 1
        assert len(izgara) * len(izgara[0]) == mesh['n_nodes']
        assert len(mesh['nodes']) == mesh['n_nodes']
        assert len(mesh['elems']) == mesh['n_elems']
        # Izgara BÜTÜN düğümleri tekrarsız kapsar (panel alanı bu haritayla
        # yerleştirir; eksik/çift indeks sessiz kaymaya yol açardı).
        duz = [n for satir in izgara for n in satir]
        assert sorted(duz) == list(range(mesh['n_nodes']))

    def test_dugum_alanlari_dugum_sayisiyla_ayni_uzunlukta(self, sentetik_sonuc):
        n = sentetik_sonuc['mesh']['n_nodes']
        assert len(sentetik_sonuc['fields']['von_mises_pa']) == n
        assert len(sentetik_sonuc['fields']['safety_factor']) == n

    def test_sf_alani_akma_bolu_von_mises(self, sentetik_sonuc):
        """SF alanı çözücünün alanıdır; uç onu yeniden ölçekleyemez."""
        yield_pa = sentetik_sonuc['scalars']['yield_strength_pa']
        assert yield_pa is not None and yield_pa > 0
        vm = np.asarray(sentetik_sonuc['fields']['von_mises_pa'], dtype=float)
        sf = np.asarray(sentetik_sonuc['fields']['safety_factor'], dtype=float)
        assert np.all(sf > 0.0)
        beklenen = yield_pa / vm
        assert np.allclose(sf, beklenen, rtol=1e-9, atol=0.0)

    def test_manset_skaleri_gauss_alanindan_gelir(self, sentetik_sonuc):
        """Manşet SF'si Gauss maksimumundan gelir — haritanınkinden farklı olabilir.

        ÖLÇÜLEN (2026-08-04, sentetik hibrit koşusu): skaler min SF 4,3576
        iken ÇİZİLEN düğüm alanının en küçüğü 4,3488 idi. Fark küçük ama
        gerçektir: skaler ``akma / max_von_mises`` (Gauss noktaları)
        tanımlıdır, harita ise SPR ile düğümlere geri kazanılmış alandır ve
        sınırda Gauss değerlerini aşabilir. Bekçi bu farkı 'kusur' diye
        kilitlemez; MANŞETİN KAYNAĞINI kilitler — panel manşeti Gauss
        temeliyle etiketler (fea_panel.js rozetleri).
        """
        sk = sentetik_sonuc['scalars']
        beklenen = sk['yield_strength_pa'] / sk['von_mises_gauss_max_pa']
        assert sk['min_safety_factor'] == pytest.approx(beklenen, rel=1e-9)
        assert min(sentetik_sonuc['fields']['safety_factor']) > 0.0

    def test_yakinsama_gecmisi_gercek(self, sentetik_sonuc):
        conv = sentetik_sonuc['convergence']
        hist = conv['history']
        assert len(hist) >= 2, 'yakınsama grafiği için en az iki tur gerekir'
        elemanlar = [h['n_elems'] for h in hist]
        assert elemanlar == sorted(elemanlar)
        assert elemanlar[-1] == sentetik_sonuc['mesh']['n_elems']
        assert hist[0]['rel_change'] is None       # ilk turun karşılaştırması yok
        assert all(h['max_von_mises'] > 0 for h in hist)
        assert isinstance(conv['converged'], bool)
        assert conv['beyan'], 'yakınsama beyanı boş olamaz'

    def test_beyan_zinciri_var(self, sentetik_sonuc):
        meta = sentetik_sonuc['meta']
        assert meta['_source'].startswith('hrma.fea.bridge')
        assert meta['girdiler'], 'girdi beyan zinciri taşınmıyor'
        assert isinstance(meta['not_modelled'], list) and meta['not_modelled']
        assert sentetik_sonuc['fields']['_basis']

    def test_birim_beyani_ve_skalerler(self, sentetik_sonuc):
        assert sentetik_sonuc['mesh']['coordinate_units'] == 'm'
        sk = sentetik_sonuc['scalars']
        assert sk['von_mises_gauss_max_pa'] > 0
        assert sk['material_key'] == 'ss_304'
        assert sk['wall_thickness_m'] == pytest.approx(0.003)
        assert sk['inner_pressure_pa'] == pytest.approx(30.0 * 1e5)


# ---------------------------------------------------------------------------
# 3. Eleman kalite ölçütleri
# ---------------------------------------------------------------------------
class TestKalite:
    def test_olcutler_matematiksel_siniri_asmiyor(self, sentetik_sonuc):
        q = sentetik_sonuc['quality']
        ar = np.asarray(q['aspect_ratio'], dtype=float)
        sj = np.asarray(q['scaled_jacobian'], dtype=float)
        n = sentetik_sonuc['mesh']['n_elems']
        assert ar.shape == (n,) and sj.shape == (n,)
        # En-boy oranı max/min olduğu için >= 1; ölçekli Jacobian köşe
        # açısının sinüsü olduğu için <= 1 ve mesh üreticisi pozitif köşe
        # Jacobian'ı garanti ettiği için > 0.
        assert np.all(ar >= 1.0 - 1e-12)
        assert np.all(sj > 0.0) and np.all(sj <= 1.0 + 1e-12)

    def test_esikler_sayi_olarak_geliyor(self, sentetik_sonuc):
        th = sentetik_sonuc['quality']['thresholds']
        assert isinstance(th['aspect_ratio_max'], (int, float))
        assert isinstance(th['scaled_jacobian_min'], (int, float))
        assert th['aspect_ratio_max'] > 1.0
        assert 0.0 < th['scaled_jacobian_min'] < 1.0

    def test_sayimlar_dizilerle_tutarli(self, sentetik_sonuc):
        q = sentetik_sonuc['quality']
        th = q['thresholds']
        ar = np.asarray(q['aspect_ratio'], dtype=float)
        sj = np.asarray(q['scaled_jacobian'], dtype=float)
        ar_kotu = ar > th['aspect_ratio_max']
        sj_kotu = sj < th['scaled_jacobian_min']
        assert q['counts']['aspect_ratio_flagged'] == int(ar_kotu.sum())
        assert q['counts']['scaled_jacobian_flagged'] == int(sj_kotu.sum())
        assert q['counts']['flagged'] == int((ar_kotu | sj_kotu).sum())
        assert q['counts']['n_elems'] == sentetik_sonuc['mesh']['n_elems']
        assert q['worst']['aspect_ratio_max'] == pytest.approx(float(ar.max()))
        assert q['worst']['scaled_jacobian_min'] == pytest.approx(float(sj.min()))

    def test_kalite_kaynak_kunyesi_beyan_ediliyor(self, sentetik_sonuc):
        basis = sentetik_sonuc['quality']['_basis']
        for parca in ('Verdict', 'SAND2007-1751', 'aspect ratio',
                      'scaled Jacobian'):
            assert parca in basis, f"kalite künyesinde '{parca}' yok"


# ---------------------------------------------------------------------------
# 4. Sahte veri yasağı — eksik girdi RED
# ---------------------------------------------------------------------------
class TestEksikGirdi:
    def test_bos_motor_not_modelled_200(self, client):
        kod, govde = kos(client, {'thrust': 1234.0})
        assert kod == 200
        fea = govde['fea']
        assert fea['status'] == 'NOT_MODELLED'
        assert fea['missing'], 'eksikler adlandırılmamış'
        assert fea['reason']
        assert fea['warning']['code'].startswith('warn.')
        for alan in FEA_REDDE_BULUNMAYACAK_ALANLAR:
            assert alan not in fea, f"redli gövdede '{alan}' bulunmamalı"

    def test_kontursuz_motor_konturu_adlandirir(self, client):
        motor = sentetik_hibrit_motor()
        motor.pop('nozzle_contour')
        kod, govde = kos(client, motor)
        assert kod == 200
        fea = govde['fea']
        assert fea['status'] == 'NOT_MODELLED'
        assert any('nozzle_contour' in m for m in fea['missing'])
        assert 'mesh' not in fea

    def test_malzemesiz_motor_malzemeyi_adlandirir(self, client):
        motor = sentetik_hibrit_motor()
        motor['structural_analysis']['design_parameters']['material'] = 'yok_boyle_bir_malzeme'
        kod, govde = kos(client, motor)
        assert kod == 200
        assert govde['fea']['status'] == 'NOT_MODELLED'
        assert any('malzeme' in m.lower() for m in govde['fea']['missing'])

    def test_govde_bos_ise_400(self, client):
        resp = _quiet(client.post, FEA_ENDPOINT, json={})
        assert resp.status_code == 400
        assert resp.get_json()['status'] == 'error'


# ---------------------------------------------------------------------------
# 5. Çözücü hatası = 500 (boş ama 'başarılı' yanıt yok)
# ---------------------------------------------------------------------------
class TestCozucuHatasi:
    def test_mesh_uretilemeyen_geometri_500(self, client):
        """z boyunca geri dönen kontur: mesh üreticisi bunu REDDEDER."""
        motor = sentetik_hibrit_motor()
        pts = motor['nozzle_contour']['points']
        bozuk = list(pts)
        bozuk[len(bozuk) // 2] = [bozuk[0][0] - 0.05, bozuk[len(bozuk) // 2][1]]
        motor['nozzle_contour']['points'] = bozuk
        kod, govde = kos(client, motor)
        assert kod == 500, govde
        assert govde['status'] == 'error'
        assert govde['detail'], 'çözücü hatasının gerekçesi taşınmıyor'
        assert 'fea' not in govde


# ---------------------------------------------------------------------------
# 6. Uzun koşu sınırı
# ---------------------------------------------------------------------------
class TestSinir:
    def test_eleman_sayisi_sinirin_altinda(self, sentetik_sonuc):
        limits = sentetik_sonuc['limits']
        assert sentetik_sonuc['mesh']['n_elems'] <= limits['max_elems']
        assert limits['clamped'] is False

    def test_asiri_istek_tur_sayisini_kisar_ve_beyan_eder(self, client):
        """Sınır aşılacaksa TUR kısılır ve bu beyan edilir (sessiz değil).

        Kısıtlama redli gövdede de taşındığı için çözücü koşturulmadan
        sınanabilir — bekçi hızlı kalır.
        """
        kod, govde = kos(client, {'thrust': 1.0},
                         n_axial0=256, n_radial0=32, max_rounds=8)
        assert kod == 200
        limits = govde['fea']['limits']
        assert limits['clamped'] is True
        assert limits['rounds_allowed'] < limits['rounds_requested']
        son = (limits['n_axial0'] * limits['n_radial0']
               * limits['refine_factor'] ** (2 * limits['rounds_allowed']))
        assert son <= limits['max_elems']
