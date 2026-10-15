"""ÖH Dalga-15 · kulvar fea-viz · aşama 1 — sekiz onarımın bekçisi.

NE KİLİTLENİR (her sınıf bir kalem; her iddia ÖLÇÜLMÜŞ bir kusurdan gelir;
ölçüm betiği ``docs/scofield/raw/OH/D15/fea-viz/a1/olcum.py``, ham sayılar
aynı dizindeki ``once_*.json`` / ``sonra_*.json`` dosyalarında)

P8B1-01  Emniyet katsayısı hükmü Gauss maksimumundan DEĞİL düğüm/SPR
         alanından türetilir. Taban ölçümü (Lamé kalın cidar çapası,
         analitik SF 8,7600): 64 elemanda yayımlanan SF 9,68099 ⟷ düğüm
         alanının en küçüğü 9,07390 — yayımlanan sayı analitikten
         +%10,51 İYİMSER ve aynı yanıttaki ``safety_factor_nodal``
         alanının minimumunun ÜSTÜNDE, yani ürün kendi kendisiyle
         çelişiyordu. Gauss maksimumu O(h¹), düğüm maksimumu O(h²)
         yakınsıyor (hata %-9,51 → %-1,28 ⟷ %-3,46 → %-0,07).
         Ürün yüzü de kilitlenir: uç ``von_mises_nodal_max_pa`` yayımlar,
         hüküm o alandan gelir ve manşet rozetinin kaynak eki SUNUCUNUN
         beyanından basılır (panel "Gauss" diye kendi başına etiketlemez).

P8B2-01  h(z) profilinin büyüklük mertebesi motorun KENDİ boğaz gaz-tarafı
         katsayısına karşı sınanır. Tabanda kapı yalnız isfinite + >0 idi:
         Bartz'ın 1/50'si verilince tepe cidar 2.587,47 K → 419,92 K
         düşüyor, "cidar eriyor" hükmü sessizce "sorun yok"a dönüyor
         (uyarı 1 → 0) ve 1e-9 çarpanında çözüm ortam sıcaklığını
         (293,15 K) aynen geri verirken hâlâ ``status='ok'`` basıyordu.

P8B2-02  Profilin KENDİ künyesi ve uyarıları köprüde düşmez; profil
         çözünürlüğünü YETERSİZ ilan etmişse (``resolution_ok = False``)
         koşu REDDEDİLİR. Tabanda yedi künye izinin YEDİSİ de köprü
         çıktısında yoktu ve y+ = 99 beyanına rağmen hüküm basılıyordu.

P8B2-03  Malzeme sıcaklık sınırı aynı DB kaydındaki adaylardan EN SIKI
         olanından verilir. Tabanda alan ADINA bakılıyordu: steel_4130
         1000 ⟷ 811 K, steel 1073 ⟷ 811 K, copper 1000 ⟷ 723 K — üçünde
         de GEVŞEK olan seçiliyor ve 855,91 K'lik tepe cidar sıcaklığı
         "sınır aşılmadı" + 0 uyarı basıyordu.

P8B2-05  Motor cidar sıcaklığına derate edilmiş akma yayımlamışsa köprü
         ONU kullanır. Tabanda sıvıda 1.100 MPa (oda) alınıyordu, motorun
         kendi kullandığı 958,155 MPa iken: dayanımda %14,80 iyimserlik,
         yayımlanan SF 1,24024 ⟷ dürüst 1,08031.

P8B2-06  STAR kesitinin varsayılan/kırpılan beyanı motorun FİİLEN
         kullandığı değerden üretilir. Tabanda ölçüt "anahtar çağıranın
         sözlüğünde var mı" idi: ``star_radius = 0,5`` mm istenip 15,000
         mm kullanılıyor, beyan ise "hiçbir alan varsayılana düşmedi,
         hiçbir alan kırpılmadı" diyordu.

P8B2-09  Rijit-cisim kısıtının yeri hükmü çeviriyor ve beyansızdı.
         Tabanda aynı motor + aynı mesh, yalnız ``axial_fix`` değişik:
         sıvı 1,24024 ⟷ 0,91104 (PASS/FAIL sınırını GEÇİYOR), katı
         3,00268 ⟷ 1,03381, hibrit 36,99854 ⟷ 21,30448; beyan alanı YOKTU
         (``meta.kisit_duyarliligi`` None, "axial_fix" metni meta'da hiç
         geçmiyordu). Artık iki kip de çözülür, KÖTÜMSER olan yayımlanır.

P8B2-10  Aynı boğaz için motorun yayımladığı rakip h_g / ısı akısı
         değerleri beyan edilir ve ayrışma ORTAK birimden hesaplanır.
         Tabanda hiçbiri yoktu; ham alanlar birimce karışık olduğu için
         çarpansız oran 4,92e6 gibi anlamsız bir sayı veriyordu (gerçek
         ayrışma 4,92×).

YÖNTEM
------
Bekçi sayı KİLİTLEMEZ: hiçbir gerilme/SF/sıcaklık sabit bir değere
bağlanmamıştır. Kilitlenen şey, kusurun kendisini gösteren İLİŞKİDİR
(hangi alandan türetildiği, hangi girdinin reddedildiği, hangi beyanın
taşındığı). Motor çözücüsü koşulmaz; girdi ``tests/test_fea_endpoint.py``
içindeki sentetik hibrit sözlüktür (alanları gerçek kontur örnekleyicisi
ve gerçek malzeme kaydından gelir) — böylece bekçi motor katmanının o
günkü durumuna bağımlı olmaz.
"""

import contextlib
import io
import warnings

import numpy as np
import pytest

warnings.filterwarnings('ignore')

# Bekçi mesh'i: işimiz sayısal hassasiyet değil (o
# tests/fea/test_yapisal_dogrulama.py'nin işi), zincirin sadakati.
D15A1_YAPISAL_MESH = {'n_axial0': 10, 'n_radial0': 3, 'max_rounds': 1}
D15A1_TERMAL_MESH = {'n_axial': 10, 'n_radial': 3}


def _sessiz(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def bridge():
    from hrma.fea import bridge as b
    return b


@pytest.fixture(scope='module')
def SA():
    from hrma.fea import structural_axisym as sa
    return sa


@pytest.fixture(scope='module')
def motor():
    """Sentetik hibrit motor sözlüğü (gerçek kontur + gerçek malzeme)."""
    from tests.test_fea_endpoint import sentetik_hibrit_motor
    # Termal yol yanma süresi ister; alan motorun kendi üst düzey
    # anahtarıdır (uydurma bir sabit değil, hibrit koşusunun girdisi).
    return sentetik_hibrit_motor(burn_time=10.0)


@pytest.fixture(scope='module')
def yapisal(bridge, motor):
    o = _sessiz(bridge.run_structural_from_motor, motor, **D15A1_YAPISAL_MESH)
    assert o['status'] == 'ok', o
    return o


@pytest.fixture(scope='module')
def profil(motor):
    """Cidar profili: motorun KENDİ h_g'sinden kurulan makul bir h(z).

    Uydurma değil — tepe değer motorun ``heat_transfer_analysis`` boğaz
    katsayısıdır, kenarlara doğru ölçeklenir. Kapı (P8B2-01) çapasını
    motorun kendi alanından aldığı için bekçinin girdisi de oradan gelir.
    """
    return _profil_kur(motor, _bogaz_hg(motor))


def _bogaz_hg(motor):
    return ((motor.get('heat_transfer_analysis') or {})
            .get('heat_transfer_coefficients') or {}).get('gas_side')


def _profil_kur(motor, hg_bogaz):
    """h(z): ekseni MOTORUN KENDİ konturundan, tepesi motorun h_g'sinden.

    Köprü profilin eksenini kontur boyuyla karşılaştırır (başka
    geometrinin profili taşınmaz), o yüzden eksen uydurulmaz — motorun
    yayımladığı kontur noktalarından okunur. Tepe (boğaz) değeri de
    motorun kendi gaz-tarafı katsayısıdır; şekil yalnız kenarlara doğru
    inen bir zarftır ve mertebeyi değiştirmez.
    """
    pts = np.asarray((motor.get('nozzle_contour') or {}).get('points'),
                     dtype=float)
    z_mm = pts[:, 0] * 1000.0
    x = np.linspace(float(z_mm.min()), float(z_mm.max()), 25)
    i_bogaz = int(np.argmin(pts[:, 1]))
    z_bogaz = float(z_mm[i_bogaz])
    genislik = max((float(z_mm.max()) - float(z_mm.min())) / 5.0, 1.0)
    sekil = 0.35 + 0.65 * np.exp(-((x - z_bogaz) / genislik) ** 2)
    return {
        'x_mm': [float(v) for v in x],
        'h_g': [float(hg_bogaz * v) for v in sekil],
        'T_recovery': [2800.0] * len(x),
    }


@pytest.fixture(scope='module')
def termal_motor(motor):
    """Motor sözlüğüne GERÇEK alan adlarıyla rakip boğaz değerleri ekler.

    Değerler motorun kendi yayımladığı büyüklük mertebesindedir; amaç
    P8B2-01 kapısına ve P8B2-10 beyanına gerçek alan adlarını vermektir.
    """
    m = dict(motor)
    m['heat_transfer_analysis'] = {
        'heat_transfer_coefficients': {'gas_side': 11524.324159039159},
        'gas_side_analysis': {'throat_heat_flux': 27104914.874968674},
        'wall_analysis': {'design_heat_flux': 27104914.874968674},
    }
    m['thermal_protection'] = {
        'nozzle_entry_liner': {'h_gas_W_m2K': 11628.973344525271},
    }
    m['nozzle_material_analysis'] = {
        'throat_thermal': {'throat_heat_flux_MW_m2': 5.506115202412987},
    }
    return m


@pytest.fixture(scope='module')
def termal_profil(termal_motor):
    return _profil_kur(termal_motor, _bogaz_hg(termal_motor))


def _termal(bridge, motor, profil, **ek):
    p = dict(profil)
    p.update(ek.pop('profil_ek', {}))
    return _sessiz(bridge.run_thermal_from_motor, motor, axial_profile=p,
                   ambient_temperature_K=293.15, **D15A1_TERMAL_MESH, **ek)


# =====================================================================
# P8B1-01 — hüküm sayısı düğüm/SPR alanından
# =====================================================================
class TestP8B1_01_HukumDugumAlanindan:

    @pytest.fixture(scope='class')
    def lame(self, SA):
        """Lamé kalın cidar çapası: analitik tepe von Mises bilinir."""
        from hrma.fea.mesh_axisym import build_wall_mesh
        a, b, p = 0.050, 0.080, 10.0e6
        mat = SA.Material(E=200e9, nu=0.3, yield_strength=250e6, name='celik')
        sr = p * a ** 2 / (b ** 2 - a ** 2) * (1 - b ** 2 / a ** 2)
        st = p * a ** 2 / (b ** 2 - a ** 2) * (1 + b ** 2 / a ** 2)
        sz = 0.3 * (sr + st)
        vm_an = float(np.sqrt(0.5 * ((sr - st) ** 2 + (st - sz) ** 2
                                     + (sz - sr) ** 2)))
        mesh = build_wall_mesh([(0.0, a), (0.30, a)], b - a, 16, 4)
        res = _sessiz(SA.solve_pressure, mesh, mat, p, axial_fix='both_ends')
        return res, vm_an, mat

    def test_cozucu_dugum_maksimumunu_yayimlar(self, lame):
        res, _vm_an, _mat = lame
        assert res.max_von_mises_nodal is not None
        assert res.max_von_mises_nodal == pytest.approx(
            float(np.max(res.von_mises_nodal)), rel=1e-12)

    def test_min_sf_dugum_maksimumundan_gauss_degil(self, lame):
        """Hüküm sayısı = akma / düğüm maksimumu = min(SF alanı)."""
        res, _vm_an, mat = lame
        # ÇEVRİLDİ (ÖH D25, OH-D24-01): hüküm sayısı ASME BPVC VIII-2 Bölüm 5
        # / Ek 5-A lineerleştirmesinden geliyor (max(1,5·P_m, P_L+P_b)).
        # Ham düğüm tepesi ASME'nin TEPE (F) sınıfıdır ve geometrik
        # süreksizlikte mesh inceltmesiyle YAKINSAMAZ (ölçülen mertebe
        # p ≈ 0,12; kanıt docs/scofield/raw/OH/D25/fea-cfd/a1/
        # teshis_scl.json); Tablo 5.6 onu plastik çökme hükmünden
        # dışlar. Alanla tek-kaynak sözleşmesi KAYBOLMADI: ham tepeden
        # türeyen sayı tepe_emniyet_katsayisi / peak_safety_factor
        # adıyla yayımlanıyor ve BURADA sınanıyor.
        beklenen = mat.yield_strength / res.max_von_mises_nodal
        assert res.tepe_emniyet_katsayisi == pytest.approx(beklenen,
                                                           rel=1e-12)
        assert res.min_safety_factor == pytest.approx(
            mat.yield_strength / res.max_von_mises_hukum, rel=1e-12)
        # ... ve aynı yanıttaki alanla BİREBİR aynı sayı (ürün artık
        # kendi kendisiyle çelişmiyor; tabanda yayımlanan sayı bunun
        # üstündeydi).
        assert res.tepe_emniyet_katsayisi == pytest.approx(
            float(np.min(res.safety_factor_nodal)), rel=1e-12)
        # Gauss maksimumundan türetilen ESKİ sayı bu mesh'te ölçülebilir
        # biçimde daha İYİMSERDİ; kaynak gerçekten değişmiş olmalı.
        # (Kıyas TEPE katsayısına karşı yapılır: P8B1-01'in kilitlediği
        # ayrım "Gauss ⟷ düğüm/SPR" ayrımıdır, ASME sınıflandırması
        # değil — OH-D24-01 o ayrımın ÜSTÜNE geldi, yerine geçmedi.)
        eski = mat.yield_strength / res.max_von_mises
        assert eski > res.tepe_emniyet_katsayisi * (1.0 + 1e-6), (
            'Gauss ve düğüm maksimumları ayırt edilemiyor — bu mesh '
            'kusuru gösteremez, bekçi anlamsızlaşır')

    def test_dugum_maksimumu_analitige_daha_yakin(self, lame):
        """Düğüm alanı tepe gerilmeyi Gauss'tan daha doğru ölçer."""
        res, vm_an, _mat = lame
        assert abs(res.max_von_mises_nodal - vm_an) < abs(
            res.max_von_mises - vm_an)

    def test_yakinsama_hedefi_hukmun_alani(self, yapisal):
        """Yakınsama ölçütü hükmü taşıyan büyüklükte tutulur."""
        hist = yapisal['convergence']['history']
        assert hist, 'yakınsama geçmişi boş'
        for h in hist:
            # Gauss maksimumu SİLİNMEZ, yanında durur...
            assert 'max_von_mises_gauss' in h
            # ... ama hedef büyüklük Gauss DEĞİLDİR.
            assert h['max_von_mises'] != pytest.approx(
                h['max_von_mises_gauss'], rel=1e-9)

    def test_urun_paketi_dugum_maksimumunu_tasir(self, yapisal):
        assert yapisal['von_mises_nodal_max'] is not None
        vm_n = np.asarray(yapisal['von_mises_nodal'], dtype=float)
        assert yapisal['von_mises_nodal_max'] == pytest.approx(
            float(vm_n.max()), rel=1e-12)
        # ÇEVRİLDİ (ÖH D25, OH-D24-01): hüküm sayısı ASME BPVC VIII-2 Bölüm 5
        # / Ek 5-A lineerleştirmesinden geliyor (max(1,5·P_m, P_L+P_b)).
        # Ham düğüm tepesi ASME'nin TEPE (F) sınıfıdır ve geometrik
        # süreksizlikte mesh inceltmesiyle YAKINSAMAZ (ölçülen mertebe
        # p ≈ 0,12; kanıt docs/scofield/raw/OH/D25/fea-cfd/a1/
        # teshis_scl.json); Tablo 5.6 onu plastik çökme hükmünden
        # dışlar. Alanla tek-kaynak sözleşmesi KAYBOLMADI: ham tepeden
        # türeyen sayı tepe_emniyet_katsayisi / peak_safety_factor
        # adıyla yayımlanıyor ve BURADA sınanıyor.
        sf = np.asarray(yapisal['safety_factor_nodal'], dtype=float)
        assert yapisal['tepe_emniyet_katsayisi'] == pytest.approx(
            float(sf.min()), rel=1e-9)

    def test_uc_dugum_maksimumunu_ve_kaynagini_yayimlar(self):
        """Ürün yüzü: uç hüküm alanını + kaynak beyanını basar."""
        from tests.test_fea_endpoint import kos, sentetik_hibrit_motor
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            kod, govde = kos(c, sentetik_hibrit_motor(),
                             n_axial0=10, n_radial0=3, max_rounds=1)
        assert kod == 200, govde
        sk = govde['fea']['scalars']
        assert sk['von_mises_nodal_max_pa'] is not None
        # ÇEVRİLDİ (ÖH D25, OH-D24-01): hüküm sayısı ASME Ek 5-A
        # lineerleştirmesinden gelir; ham tepeden türeyen sayı
        # peak_safety_factor adıyla yayımlanır ve BURADA sınanır.
        assert sk['peak_safety_factor'] == pytest.approx(
            sk['yield_strength_pa'] / sk['von_mises_nodal_max_pa'], rel=1e-9)
        # Kaynak SUNUCUDAN gelir; panel kendi başına "Gauss" etiketlemez.
        assert sk['headline_source'], 'manşet kaynağı beyan edilmiyor'
        assert 'nodal' in sk['headline_source'].lower()
        assert 'von_mises_nodal_max_pa' in sk['_basis']

    def test_panel_rozet_kaynagini_sunucudan_alir(self):
        """fea_panel.js manşet rozetine kaynağı SUNUCU yazar."""
        import pathlib
        js = pathlib.Path(__file__).resolve().parents[1] / (
            'hrma/static/js/fea_panel.js')
        metin = js.read_text(encoding='utf-8')
        assert 'function kaynakliRozet' in metin
        # Rozetler kaynak ekini sabit metinden DEĞİL sunucudan alır.
        assert metin.count('kaynakliRozet(TF(') >= 2
        assert 'headline_source: scalars.headline_source' in metin
        # Manşet skaleri hüküm alanından okunur.
        assert 'von_mises_max_mpa: isNum(scalars.von_mises_nodal_max_pa)' \
            in metin


# =====================================================================
# P8B2-01 — h(z) makullük kapısı
# =====================================================================
class TestP8B2_01_HgMakullukKapisi:

    def test_makul_profil_gecer(self, bridge, termal_motor, termal_profil):
        o = _termal(bridge, termal_motor, termal_profil)
        assert o['status'] == 'ok', o.get('reason')
        kapi = o['meta']['girdiler']['h_profili']['makulluk_kapisi']
        assert kapi['durum'] == 'gecti'
        assert kapi['bagil_sapma'] <= kapi['tolerans']

    @pytest.mark.parametrize('carpan', [1.0 / 50.0, 1.0 / 99.0, 1e-9, 50.0])
    def test_mertebe_disi_profil_reddedilir(self, bridge, termal_motor,
                                            termal_profil, carpan):
        """Mertebe dışı h(z) ile HÜKÜM ÇIKARILMAZ (fail-closed)."""
        p = dict(termal_profil)
        p['h_g'] = [v * carpan for v in termal_profil['h_g']]
        o = _termal(bridge, termal_motor, p)
        assert o['status'] != 'ok', (
            'mertebe dışı h(z) kabul edildi — cidar sıcaklığı hükmü '
            'sessizce çevrilebilir')
        assert 'axial_profile.h_g' in ' '.join(o.get('missing') or [])
        assert o.get('reason')
        # Sahte veri yasağı: redli gövdede sıcaklık alanı BULUNMAZ.
        for alan in ('temperature_nodal', 'material_limits', 'mesh'):
            assert alan not in o

    def test_capa_yoksa_kapi_calistirilamadi_diye_beyan_edilir(
            self, bridge, termal_motor, termal_profil):
        """Motor h_g yayımlamıyorsa uydurma çapa konmaz, beyan edilir."""
        m = {k: v for k, v in termal_motor.items()
             if k not in ('heat_transfer_analysis', 'thermal_protection')}
        assert _bogaz_hg(m) is None
        p = dict(termal_profil)
        o = _termal(bridge, m, p)
        if o['status'] != 'ok':
            pytest.skip('bu girdi başka bir kapıdan döndü: '
                        + str(o.get('reason'))[:120])
        kapi = o['meta']['girdiler']['h_profili']['makulluk_kapisi']
        assert kapi['durum'] == 'calistirilamadi'
        assert kapi['beyan']


# =====================================================================
# P8B2-02 — profilin kendi künyesi ve çekincesi
# =====================================================================
class TestP8B2_02_ProfilKunyesi:

    def test_kunye_alanlari_kopruden_gecer(self, bridge, termal_motor,
                                           termal_profil):
        p = dict(termal_profil)
        p['_source'] = 'D15-bekci-kaynak'
        p['contour_basis'] = {'kaynak': 'D15-bekci-kontur'}
        p['y_plus_max'] = 12.5
        p['warnings'] = [{'code': 'warn.cfd.wall_resolution',
                          'params': {'y_plus': 12.5}}]
        o = _termal(bridge, termal_motor, p)
        assert o['status'] == 'ok', o.get('reason')
        sinir = o['meta']['girdiler']['h_profili']
        kunye = sinir['profil_kunyesi']
        assert isinstance(kunye, dict)
        for ad in ('_source', 'contour_basis', 'y_plus_max'):
            assert ad in kunye, f'{ad} köprüde düşüyor'
        assert kunye['_source'] == 'D15-bekci-kaynak'
        # Profilin KENDİ uyarısı da taşınır (yeniden yorumlanmadan).
        kodlar = [w.get('code') for w in sinir['profil_uyarilari']]
        assert 'warn.cfd.wall_resolution' in kodlar

    def test_kunye_alani_HER_ZAMAN_sozluk(self, bridge, termal_motor,
                                          termal_profil):
        """``profil_kunyesi`` tipi, içeriğin dolu olmasına göre DEĞİŞMEZ.

        ÖH D28 fix-28b (taban kaydı-12'nin 6 kırmızısı). Alan BİRLEŞİK
        TİPTİ: çağıranın profili x_mm/h_g/T_recovery dışında anahtar
        taşımıyorsa köprü sözlük yerine düz METİN yazıyordu. D26 fea-cfd a3
        (fc55be6a, P8B1-11) alanı okuyan tüketiciyi eklerken sözlük
        varsaydı; künyesiz profil gelen her koşum ``AttributeError: 'str'
        object has no attribute 'get'`` ile düştü (bridge.py:2484) ve bu
        dosyada 6 test birden kırmızıydı. Onarım tüketicide değil
        SÖZLEŞMEDE yapıldı: alan her iki dalda da sözlüktür.

        Bu bekçi iki dalı da ölçer; ``termal_profil`` fikstürü tam olarak o
        boş dalı üretir (yalnız üç dizi taşır), yani düz metne dönüş
        buradan kırmızı verir.
        """
        o = _termal(bridge, termal_motor, termal_profil)
        assert o['status'] == 'ok', o.get('reason')
        kunye = o['meta']['girdiler']['h_profili']['profil_kunyesi']
        assert isinstance(kunye, dict), (
            'künyesiz profil dalında alan %s döndü — tip içeriğe göre '
            'değişemez, tüketici .get() çağırıyor' % type(kunye).__name__)
        # Beyan kaybolmadı: boş dalda da köprünün kendi cümlesi duruyor.
        assert 'BİLİNMİYOR' in str(kunye.get('_basis', '')), (
            'boş künye dalında köprünün beyanı düştü: %r' % (kunye,))

    def test_dogrulanmamis_cozunurluk_reddedilir(self, bridge, termal_motor,
                                                 termal_profil):
        """resolution_ok = False ise hüküm YAYIMLANMAZ."""
        p = dict(termal_profil)
        p['resolution_ok'] = False
        p['y_plus_max'] = 99.0
        o = _termal(bridge, termal_motor, p)
        assert o['status'] != 'ok'
        assert 'resolution_ok' in ' '.join(o.get('missing') or [])
        assert 'material_limits' not in o

    def test_cozunurluk_dogrulanmissa_gecer(self, bridge, termal_motor,
                                            termal_profil):
        p = dict(termal_profil)
        p['resolution_ok'] = True
        o = _termal(bridge, termal_motor, p)
        assert o['status'] == 'ok', o.get('reason')


# =====================================================================
# P8B2-03 — sıcaklık sınırı: SIKI olan seçilir
# =====================================================================
class TestP8B2_03_SicaklikSiniri:

    CELISKILI = ('steel_4130', 'steel', 'copper')

    @pytest.mark.parametrize('ad', CELISKILI)
    def test_siki_aday_secilir(self, bridge, ad):
        from hrma.data.materials_db import get_material
        rec = _sessiz(get_material, ad)
        adaylar = [float(rec[k]) for k in
                   ('allowable_temperature', 'max_service_temp')
                   if rec.get(k) is not None]
        if len(adaylar) < 2 or abs(max(adaylar) - min(adaylar)) < 1e-9:
            pytest.skip(f'{ad} kaydında çelişki yok')
        alanlar, _b = _sessiz(bridge._extract_thermal_material, ad)
        assert alanlar['allowable_temperature_K'] == pytest.approx(
            min(adaylar), rel=1e-9), (
            f'{ad}: emniyet hükmü GEVŞEK alandan veriliyor')
        # Atlanan alan adıyla ve değeriyle BEYAN edilir (gizlenmez).
        assert len(alanlar['allowable_temperature_adaylari_K']) == 2
        assert alanlar['allowable_temperature_alani']
        assert 'atlanan' in alanlar['allowable_temperature_kaynagi']

    def test_uc_yayini_secim_beyanini_tasir(self, bridge, termal_motor,
                                            termal_profil):
        o = _termal(bridge, termal_motor, termal_profil)
        assert o['status'] == 'ok', o.get('reason')
        ml = o['material_limits']
        assert ml['allowable_temperature_adaylari_K'] is not None
        assert ml['allowable_temperature_kaynagi']
        if ml['allowable_temperature_K'] is not None:
            adaylar = ml['allowable_temperature_adaylari_K']
            assert ml['allowable_temperature_K'] == pytest.approx(
                min(adaylar.values()), rel=1e-9)

    def test_sinir_yoksa_uydurulmaz(self, bridge, monkeypatch):
        """Kayıtta sınır yoksa sayı UYDURULMAZ, yokluk beyan edilir."""
        import hrma.data.materials_db as db
        monkeypatch.setattr(db, 'get_material', lambda ad: {
            'elastic_modulus': 200e9, 'poisson_ratio': 0.3,
            'thermal_conductivity': 45.0, 'specific_heat': 460.0,
            'density': 7800.0})
        alanlar, beyan = _sessiz(bridge._extract_thermal_material, 'ss_304')
        assert alanlar is not None, beyan
        assert alanlar['allowable_temperature_K'] is None
        assert alanlar['allowable_temperature_adaylari_K'] == {}
        assert 'uydurulmaz' in alanlar['allowable_temperature_kaynagi']


# =====================================================================
# P8B2-05 — akma: derate edilmiş değer varsa O kullanılır
# =====================================================================
class TestP8B2_05_DerateAkma:

    @staticmethod
    def _sivi(y_oda, y_cidar):
        return {
            'chamber_pressure': 70.0,
            'structural_analysis': {
                'chamber_structure': {
                    'material_key': 'stainless_304',
                    'yield_strength': y_oda,
                    'yield_strength_at_wall_temp': y_cidar,
                },
            },
        }

    def test_siki_olan_alinir(self, bridge):
        mat, beyan = _sessiz(bridge._extract_material,
                             self._sivi(1100.0, 958.155), 'liquid')
        assert mat.yield_strength == pytest.approx(958.155e6, rel=1e-12), (
            'oda sıcaklığı akması alınıyor — SF ölçülü %14,80 iyimser olur')
        assert 'yield_strength_at_wall_temp' in beyan['akma_kaynagi']

    def test_derate_gevsekse_oda_degeri_kalir(self, bridge):
        """Ters yönde de SIKI olan seçilir (kural simetriktir)."""
        mat, beyan = _sessiz(bridge._extract_material,
                             self._sivi(900.0, 1200.0), 'liquid')
        assert mat.yield_strength == pytest.approx(900.0e6, rel=1e-12)
        assert 'GEVŞEK' in beyan['akma_kaynagi']

    def test_derate_yoksa_oda_degeri_ve_beyani(self, bridge):
        mat, beyan = _sessiz(bridge._extract_material,
                             self._sivi(1100.0, None), 'liquid')
        assert mat.yield_strength == pytest.approx(1100.0e6, rel=1e-12)
        assert 'yayımlamadı' in beyan['akma_kaynagi']

    def test_derating_artik_modellenmemis_sayilmaz(self, yapisal):
        """not_modelled listesi gerçeği söyler: derating modelleniyor."""
        nm = ' '.join(yapisal['meta']['not_modelled'])
        assert 'DAYANIM DERATİNGİ' in nm or 'derate' in nm


# =====================================================================
# P8B2-06 — STAR beyanı motorun KULLANDIĞI değerden
# =====================================================================
class TestP8B2_06_StarBeyani:

    @staticmethod
    def _kos(bridge, ov):
        return _sessiz(bridge.run_planar_grain_fea, 'star', 'apcp',
                       outer_diameter_mm=100.0, core_diameter_mm=40.0,
                       chamber_pressure_bar=50.0,
                       geometry_overrides=dict(ov),
                       n_theta0=8, n_radial0=3, max_rounds=1)

    def test_reddedilen_deger_beyanda_gorunur(self, bridge):
        """0,5 mm istenip 15,000 mm kullanıldıysa beyan bunu SÖYLER."""
        o = self._kos(bridge, {'star_radius': 0.5})
        assert o['status'] == 'ok', o
        geo = o['inputs']['geometri']
        iv = geo['istenen_vs_kullanilan']
        assert 'star_radius' in iv, (
            'beyan hâlâ "anahtar sözlükte var mı" ölçütünde')
        assert iv['star_radius']['istenen'] == pytest.approx(0.5)
        kullanilan = iv['star_radius']['kullanilan']
        assert kullanilan > 0.5 * 1.5, (
            'bu koşuda motor istenen değeri kullanmış — kalem bu girdiyle '
            'gösterilemez')
        # Reddedilen değer ya "varsayılana düştü" ya "kırpıldı" olarak
        # LİSTEDE görünür; sessiz kabul yok.
        listeler = (geo['varsayilan_kullanilan_alanlar']
                    + geo['kirpilan_alanlar'])
        assert 'star_radius' in listeler
        assert iv['star_radius'].get('hukum')

    def test_kabul_edilen_deger_varsayilan_diye_listelenmez(self, bridge):
        o = self._kos(bridge, {'star_radius': 10.0, 'star_points': 6})
        assert o['status'] == 'ok', o
        geo = o['inputs']['geometri']
        iv = geo['istenen_vs_kullanilan']
        assert iv['star_radius']['kullanilan'] == pytest.approx(10.0,
                                                               rel=1e-6)
        assert 'star_radius' not in geo['varsayilan_kullanilan_alanlar']
        assert 'star_radius' not in geo['kirpilan_alanlar']

    def test_reddedilen_uc_sayisi_beyanda(self, bridge):
        o = self._kos(bridge, {'star_points': 200})
        assert o['status'] == 'ok', o
        geo = o['inputs']['geometri']
        iv = geo['istenen_vs_kullanilan']
        assert iv['star_points']['istenen'] == pytest.approx(200.0)
        assert iv['star_points']['kullanilan'] != pytest.approx(200.0)
        assert 'star_points' in (geo['varsayilan_kullanilan_alanlar']
                                 + geo['kirpilan_alanlar'])

    def test_hic_istenmeyen_alan_varsayilan_listesinde(self, bridge):
        o = self._kos(bridge, {})
        assert o['status'] == 'ok', o
        geo = o['inputs']['geometri']
        assert set(geo['varsayilan_kullanilan_alanlar']) >= {
            'star_points', 'star_radius'}
        assert geo['istenen_vs_kullanilan'] == {}

    def test_beyan_olcutu_yazili(self, bridge):
        o = self._kos(bridge, {'star_radius': 0.5})
        assert 'KULLANDIĞI' in o['inputs']['geometri']['beyan_olcutu']


# =====================================================================
# P8B2-09 — kısıt yeri duyarlılığı: kötümser yayımlanır
# =====================================================================
class TestP8B2_09_KisitDuyarliligi:

    @pytest.fixture(scope='class')
    def cift(self, bridge, motor):
        o_min = _sessiz(bridge.run_structural_from_motor, motor,
                        axial_fix='z_min', **D15A1_YAPISAL_MESH)
        o_max = _sessiz(bridge.run_structural_from_motor, motor,
                        axial_fix='z_max', **D15A1_YAPISAL_MESH)
        assert o_min['status'] == 'ok' and o_max['status'] == 'ok'
        return o_min, o_max

    def test_duyarlilik_beyani_var(self, cift):
        for o in cift:
            d = o['meta']['kisit_duyarliligi']
            assert d, 'kısıt yeri duyarlılığı beyansız'
            assert d['birincil_kip'] and d['karsit_kip']
            assert d['karsit_min_safety_factor'] is not None
            assert d['yayimlanan_kip']
            assert d['_basis']

    def test_kotumser_yayimlanir(self, cift):
        for o in cift:
            d = o['meta']['kisit_duyarliligi']
            a = d['birincil_min_safety_factor']
            b = d['karsit_min_safety_factor']
            assert o['min_safety_factor'] == pytest.approx(min(a, b),
                                                           rel=1e-9)

    def test_giris_bagimliligi_daralir(self, cift):
        """Kısıt yeri seçiminin hüküm üstündeki etkisi DARALIR.

        Onarım kısıt yeri bağımlılığını SIFIRLAMAZ ve bunu iddia da
        etmez: yakınsama hâlâ birincil kiple koşulduğu için son mesh
        girişe göre değişebilir (kod bunu ``secim_beyani`` içinde
        yazıyor). Kilitlenen şey, iyimser yakanın artık hüküm olarak
        BASILAMAMASIDIR: her giriş kendi çiftinin kötümserini yayımlar,
        dolayısıyla iki girişin YAYIMLANAN sayıları arasındaki açıklık,
        ham birincil sonuçlar arasındaki açıklıktan KÜÇÜKTÜR.
        """
        o_min, o_max = cift
        ham = [o['meta']['kisit_duyarliligi']['birincil_min_safety_factor']
               for o in cift]
        yay = [o['min_safety_factor'] for o in cift]
        ham_aciklik = max(ham) / min(ham)
        yay_aciklik = max(yay) / min(yay)
        assert yay_aciklik < ham_aciklik, (
            f'yayımlanan açıklık {yay_aciklik:.4f} ham açıklık '
            f'{ham_aciklik:.4f} kadar — kötümser seçim işlemiyor')
        # Hiçbir girişte İYİMSER yaka yayımlanmaz.
        for o in cift:
            d = o['meta']['kisit_duyarliligi']
            iyimser = max(d['birincil_min_safety_factor'],
                          d['karsit_min_safety_factor'])
            assert o['min_safety_factor'] < iyimser * (1.0 - 1e-9) or \
                d['birincil_min_safety_factor'] == pytest.approx(
                    d['karsit_min_safety_factor'], rel=1e-12)
            assert d['secim_beyani']

    def test_alanlar_yayimlanan_kipten(self, cift):
        """Skaler, alan ve hüküm AYNI çözümden (iç tutarlılık)."""
        for o in cift:
        # ÇEVRİLDİ (ÖH D25, OH-D24-01): hüküm sayısı ASME BPVC VIII-2 Bölüm 5
        # / Ek 5-A lineerleştirmesinden geliyor (max(1,5·P_m, P_L+P_b)).
        # Ham düğüm tepesi ASME'nin TEPE (F) sınıfıdır ve geometrik
        # süreksizlikte mesh inceltmesiyle YAKINSAMAZ (ölçülen mertebe
        # p ≈ 0,12; kanıt docs/scofield/raw/OH/D25/fea-cfd/a1/
        # teshis_scl.json); Tablo 5.6 onu plastik çökme hükmünden
        # dışlar. Alanla tek-kaynak sözleşmesi KAYBOLMADI: ham tepeden
        # türeyen sayı tepe_emniyet_katsayisi / peak_safety_factor
        # adıyla yayımlanıyor ve BURADA sınanıyor.
            sf = np.asarray(o['safety_factor_nodal'], dtype=float)
            assert o['tepe_emniyet_katsayisi'] == pytest.approx(
                float(sf.min()), rel=1e-9)
            assert o['axial_fix_used'] == \
                o['meta']['kisit_duyarliligi']['yayimlanan_kip']

    def test_not_modelled_mesnet_beyani(self, yapisal):
        assert any('mesnet' in s or 'rijit-cisim' in s
                   for s in yapisal['meta']['not_modelled'])


# =====================================================================
# P8B2-10 — rakip boğaz değerleri ve ORTAK birimde ayrışma
# =====================================================================
class TestP8B2_10_RakipBogazDegerleri:

    def test_rakipler_beyan_edilir(self, bridge, termal_motor, termal_profil):
        o = _termal(bridge, termal_motor, termal_profil)
        assert o['status'] == 'ok', o.get('reason')
        ad = o['meta']['girdiler']['h_profili']['motor_bogaz_adaylari']
        assert len(ad['h_g_W_m2K']) >= 2, 'rakip h_g alanları beyansız'
        assert ad['h_g_ayrisma_orani'] > 1.0
        assert len(ad['isi_akisi']) >= 2
        assert ad['_basis']

    def test_ayrisma_orani_ortak_birimden(self, bridge, termal_motor,
                                          termal_profil):
        """Birimleri karışık bir oran beyan edilmez."""
        o = _termal(bridge, termal_motor, termal_profil)
        ad = o['meta']['girdiler']['h_profili']['motor_bogaz_adaylari']
        wm2 = ad['isi_akisi_W_m2']
        assert wm2, 'ortak birime çevrilmiş akış yok'
        assert ad['isi_akisi_ayrisma_orani'] == pytest.approx(
            max(wm2.values()) / min(wm2.values()), rel=1e-12)
        # MW alanı gerçekten çevrilmiş olmalı (çarpansız oran 1e6
        # mertebesinde anlamsız bir sayı veriyordu).
        assert ad['isi_akisi_ayrisma_orani'] < 1e3
        mw = [k for k in wm2 if k.endswith('MW_m2')]
        if mw:
            assert wm2[mw[0]] == pytest.approx(
                ad['isi_akisi'][mw[0]] * 1e6, rel=1e-12)

    def test_kapi_capasi_motorun_kendi_alanindan(self, bridge, termal_motor,
                                                 termal_profil):
        o = _termal(bridge, termal_motor, termal_profil)
        sinir = o['meta']['girdiler']['h_profili']
        kapi = sinir['makulluk_kapisi']
        adaylar = sinir['motor_bogaz_adaylari']['h_g_W_m2K']
        assert kapi['en_yakin_motor_alani'] in adaylar
        assert kapi['en_yakin_motor_degeri_W_m2K'] == pytest.approx(
            adaylar[kapi['en_yakin_motor_alani']], rel=1e-12)


# =====================================================================
# ÇAPA BULGUSU — meshlenemeyen inceltme sondası koşuyu ÇÖKERTMEZ
# =====================================================================
class TestCapaB3_MeshlenemeyenSonda:
    """Katı motorun yapısal ucu HTTP 500 dönmez; durum BEYAN edilir.

    ÖLÇÜLDÜ (ÖH D15 çapa koşumu, B3_fea_structural_kati): taban ağacında
    uç 200 dönüyordu ÇÜNKÜ yakınsama Gauss maksimumuyla erken duruyor ve
    bozuk mesh'e hiç ulaşılmıyordu (taban rounds=4/5/6 hepsi 'ok').
    Hüküm alanı düğüm/SPR'ye taşınınca (P8B1-01) inceltme ilerliyor,
    ``build_wall_mesh`` n_axial=2048 / n_radial=32 sondasında "dış eğri
    z'de ilerlemiyor" diye reddediyor ve ``solve_with_refinement``
    ValueError'ı yukarı geçirip ucu HTTP 500 yapıyordu — elde GEÇERLİ bir
    çözüm dururken. Kusur tabanda da vardı, yalnız görünmüyordu.

    Onarım: sonda meshlenemezse inceltme DURUR (yarım kanıtla katlama
    yok), son tam ölçülmüş tur korunur, "yakınsamadı" hükmü ve
    meshlenemeyen sondanın kendisi beyan edilir.
    """

    @pytest.fixture(scope='class')
    def kati_yanit(self):
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            kati = _sessiz(c.post, '/calculate_solid', json={
                'motor_name': 'D15-BEKCI-KATI', 'propellant_type': 'apcp',
                'grain_type': 'bates', 'chamber_pressure': 40.0,
                'thrust': 5000.0, 'burn_time': 3.0,
                'chamber_diameter': 100.0, 'grain_length': 500.0,
                'core_diameter': 30.0, 'expansion_ratio': 8.0}).get_json()
            if not isinstance(kati, dict):
                pytest.skip('/calculate_solid bu derlemede koşmuyor')
            r = _sessiz(c.post, '/api/fea/structural', json={'results': kati})
            return r.status_code, r.get_json()

    def test_uc_500_donmez(self, kati_yanit):
        kod, govde = kati_yanit
        assert kod != 500, govde
        assert kod == 200, govde

    def test_meshlenemeyen_sonda_beyanli(self, kati_yanit):
        _kod, govde = kati_yanit
        fea = govde['fea']
        if fea.get('status') != 'ok':
            pytest.skip('bu girdi köprüden redle döndü: '
                        + str(fea.get('reason'))[:120])
        conv = fea['convergence']
        hatalar = conv.get('sonda_hatalari')
        if not hatalar:
            pytest.skip('bu geometride hiçbir sonda meshlenemez duruma '
                        'gelmedi — dal ölçülemedi')
        # Beyan sessiz değil: hata adıyla ve mesh boyutuyla duruyor.
        for h in hatalar:
            assert h['sonda'] in ('eksenel', 'radyal', 'eksenel+radyal')
            assert h['n_axial'] > 0 and h['n_radial'] > 0
            assert h['hata']
        assert 'İNCELTME ERKEN DURDU' in conv['beyan']
        # Yarım kanıtla "yakınsadı" ilan edilmez.
        assert conv['converged'] is False
        # ... ve elde GEÇERLİ bir çözüm vardır (boş yanıt üretilmedi).
        assert fea['scalars']['min_safety_factor'] is not None
        assert fea['mesh']['n_elems'] > 0

    def test_sondasiz_kosuda_alan_bos_liste(self, yapisal):
        """Sorunsuz koşuda alan VARDIR ve boştur (sessiz yokluk yok)."""
        assert yapisal['meta']['yakinsama']['sonda_hatalari'] == []
        # Ürün yüzü de görsün diye yakınsama bloğunda da durur.
        assert yapisal['convergence']['sonda_hatalari'] == []
