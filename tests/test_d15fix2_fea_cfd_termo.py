# -*- coding: utf-8 -*-
"""ÖH D15 birleşme-etkileşimi düzeltmesi — küme: fea-cfd-termo.

Bu dosya, birleşme sırasında BİRBİRİNİ BOZAN iki onarımın ürün tarafındaki
uzlaşmasını kilitler. Kulvarlar ayrı worktree'lerde yeşildi; ana ağaçta
aynı uçlara/alanlara dokundukları için biri ötekinin iddiasını geçersiz
kıldı. Aşağıdaki bekçiler o uzlaşmanın geri alınmasını yakalar.

Kilitlenen üç ürün onarımı
--------------------------
1. ``/api/thermal-protection`` — bilinmeyen mod 400 yerine 500 veriyordu
   (``UnboundLocalError``: ``except HeatSinkBudgetExceeded`` yakalama
   ifadesi, gövde içindeki ``from ... import`` satırına hiç ulaşılmayan
   yollarda çözümlenemiyordu).
2. ``hrma/fea/bridge.py`` — P8B2-04 boğaz nirengisi, CFD ile ÇÖZÜLMÜŞ
   profilleri (h tepesi giriştedir) geçersiz sayıp reddediyordu; h_g
   makullük çapası da profilin global maksimumundan okunuyordu.
3. ``hrma/fea/mesh_axisym.py`` — dış yüzey eğrilik tabanının köşe düzeltme
   penceresi istasyon aralığıyla orantılıydı, yani İNCELTME TABANI GERİ
   ALIYORDU; ayrıca tabanın çözünürlükten bağımsız kanıtı hiç
   yayımlanmıyordu.

Ölçüm künyesi (1 Eylül 2026, bu depo) her bekçinin kendi docstring'inde.
"""

import numpy as np
import pytest


# ===========================================================================
# 1) /api/thermal-protection — bilinmeyen mod FAIL-CLOSED 400
# ===========================================================================
class TestTermalKorumaBilinmeyenMod:

    @pytest.fixture(scope='class')
    def client(self):
        from hrma.app import app
        app.config['TESTING'] = True
        return app.test_client()

    def test_bilinmeyen_mod_400_verir_500_degil(self, client):
        """Bilinmeyen mod istemci hatasıdır; sunucu çökmesi değil.

        ÖLÇÜLDÜ (taban 6fde52b): HTTP 500 + ``UnboundLocalError: cannot
        access local variable 'HeatSinkBudgetExceeded'``. Sebep: adlar
        ``try:`` gövdesinde, ``raise ValueError("Unknown mode ...")``
        satırından SONRA içe aktarılıyordu; ``from ... import`` adı YEREL
        yaptığı için, import'a hiç ulaşılmayan her yolda ``except
        HeatSinkBudgetExceeded`` ifadesi çözümlenemiyordu. İki kulvarın
        onarımı da doğruydu (bilinmeyen-mod kapısı ⟷ hesap bütçesi
        yakalayıcısı); çakışan tek şey adın BAĞLANMA ANIydı.
        """
        r = client.post('/api/thermal-protection', json={'mode': 'bogus'})
        assert r.status_code == 400, (
            f'bilinmeyen mod HTTP {r.status_code} verdi; 400 bekleniyor '
            '(500 ise ad bağlama kusuru geri gelmiş olabilir)')
        assert 'Unknown mode' in str((r.get_json() or {}).get('error'))

    def test_hesap_butcesi_kapisi_hala_422(self, client):
        """Kardeş kapı (P4B1-13) korunuyor: bütçe aşımı 422 + adlı alan.

        Ad bağlamayı düzeltirken bu yakalayıcının işlevini kaybetmediğini
        kilitler — iki kapı da kendi sözleşmesini sürdürmeli.
        """
        r = client.post('/api/thermal-protection', json={
            'mode': 'heat_sink', 'h_gas_W_m2K': 5000.0,
            'T_recovery_K': 3000.0, 'burn_time_s': 300.0,
            'wall_thickness_m': 0.0005, 'n_nodes': 201})
        assert r.status_code == 422, f'HTTP {r.status_code}'
        j = r.get_json()
        assert j['error'] == 'thermal_protection_compute_budget_exceeded'
        assert j['invalid_fields']


# ===========================================================================
# 2) Köprü — CFD profili KABUL, kaydırılmış profil RED
# ===========================================================================
def _hibrit_motor():
    from hrma.app import app
    app.config['TESTING'] = True
    c = app.test_client()
    return (c.post('/calculate', json={
        'motor_name': 'd15fix2', 'thrust': 2000, 'burn_time': 10,
        'of_ratio': 6.0, 'chamber_pressure': 30.0,
        'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}).get_json()
        or {}).get('motor') or {}


@pytest.fixture(scope='module')
def motor():
    return _hibrit_motor()


@pytest.fixture(scope='module')
def bartz(motor):
    """Motorun KENDİ konturu + Bartz zarfı: tepe boğazdadır (tanım gereği)."""
    import hrma.fea.bridge as BR
    gir = BR.extract_structural_inputs(motor, include_chamber=False)
    kontur = np.asarray(gir['contour'], dtype=float)
    z, r = kontur[:, 0], kontur[:, 1]
    capa = BR._motor_bogaz_adaylari(motor)['h_g_W_m2K'] or {}
    hg0 = float(list(capa.values())[0])
    return {
        'x_mm': (z * 1000.0).tolist(),
        'h_g': (hg0 * (float(np.min(r)) / r) ** 1.8).tolist(),
        'T_recovery': np.full(z.size, 2900.0).tolist(),
    }, z, r, hg0


class TestKopruBogazNirengisi:

    def test_h_tepesi_giriste_olan_profil_KABUL_EDILIR(self, motor, bartz):
        """CFD ile çözülmüş profilin tepesi boğazda DEĞİL, giriştedir.

        ÖLÇÜLDÜ (tests/cfd/test_wall_output.py viskoz_izo vakası,
        ``hrma.cfd.wall_output.thermal_axial_profile``): sınır tabakası
        girişte sıfır kalınlıktan başlar, h orada tekilliğe yakın büyür ve
        boğaza kadar TEKDÜZE azalır —

            istasyon      z [mm]     h_g [W/m²K]
            giriş (i=0)    2,344       320.560,4
            boğaz (i=25) 119,531        51.845,1     (oran 6,183)

        yani ``argmax(h) = 0``. Eski kapı bu GEÇERLİ profili "iç
        istasyonları 119,531 mm kaymış" diye reddediyor ve CFD → termal FEA
        ürün yolunu tümden kapatıyordu. Nirengi ("h tepesi boğaza düşer")
        yalnız profil KENDİ boğaz imzasını taşıyorsa (tepe İÇ istasyondaysa)
        bir boğaz iddiasıdır; tepe uçtaysa iddia YOKTUR, sınanamaz ve
        uydurulmaz — kapı "çalıştırılamadı" diye BEYAN EDER.
        """
        import hrma.fea.bridge as BR
        prof, z, r, hg0 = bartz
        h = np.asarray(prof['h_g'], dtype=float)
        i_bogaz = int(np.argmin(r))
        # Girişte tepe yapan, boğaza doğru TEKDÜZE azalan profil (CFD
        # deseni). Boğaz istasyonundaki değer motorun kendi katsayısına
        # normalize edilir; böylece h(z) MERTEBE kapısı (P8B2-01) bu
        # fikstürü suçlamaz ve sınanan şey yalnız boğaz NİRENGİSİ olur.
        # Tepe/boğaz oranı 6,7 — ölçülen CFD oranı 6,18 ile aynı mertebe.
        tt = np.linspace(0.0, 1.0, h.size)
        ham = np.exp(-3.0 * tt)
        h_cfd = hg0 * ham / float(ham[i_bogaz])
        p = dict(prof, h_g=h_cfd.tolist())
        assert int(np.argmax(h_cfd)) == 0, 'fikstür kurulmadı: tepe içeride'
        assert np.isclose(h_cfd[i_bogaz], hg0)
        assert h_cfd.max() / h_cfd[i_bogaz] > 5.0

        o = BR.extract_thermal_inputs(motor, p)
        assert o['status'] == BR.BRIDGE_STATUS_OK, (
            f"CFD deseni profil reddedildi: {o.get('reason')}")
        hiza = o['_basis']['h_profili']['bogaz_hizasi']
        assert hiza['durum'] == 'calistirilamadi'
        assert hiza['beyan'], 'nirengi uygulanamadıysa GEREKÇE yazılmalı'

    def test_ic_imzali_profil_hala_hizaya_ZORUNLU(self, motor, bartz):
        """Tepe İÇ istasyondaysa boğaza düşmek ZORUNDA (kapı gevşemedi).

        Kusur vakası: uçları AYNEN korunup ekseni t⁴ ile sıkıştırılmış
        profil. Bozma yalnız EKSENİ yeniden eşler, h dizisine dokunmaz, o
        yüzden tepe İÇ istasyonda kalır (ölçüldü: argmax = 26, bozmadan
        önce de sonra da) ve kapı onu REDDEDER — z_tepe 66,431 mm →
        10,148 mm.
        """
        import hrma.fea.bridge as BR
        prof, z, r, hg0 = bartz
        h = np.asarray(prof['h_g'], dtype=float)
        assert 0 < int(np.argmax(h)) < h.size - 1, 'fikstür: tepe içeride'

        x = np.asarray(prof['x_mm'], dtype=float)
        tt = (x - x[0]) / (x[-1] - x[0])
        bozuk = dict(prof, x_mm=(x[0] + (x[-1] - x[0]) * tt ** 4).tolist())
        o = BR.extract_thermal_inputs(motor, bozuk)
        assert o['status'] == 'NOT_MODELLED'
        assert 'boğaz hizası' in ' '.join(o['missing'])

    def test_hizali_bartz_profil_gecer_ve_hiza_OLCULUR(self, motor, bartz):
        """Sağlam Bartz profili geçer ve hizanın ÖLÇÜMÜ beyanda durur."""
        import hrma.fea.bridge as BR
        prof, z, r, hg0 = bartz
        o = BR.extract_thermal_inputs(motor, prof)
        assert o['status'] == BR.BRIDGE_STATUS_OK, o.get('reason')
        hiza = o['_basis']['h_profili']['bogaz_hizasi']
        assert hiza['durum'] == 'gecti'
        assert hiza['sapma_m'] <= hiza['tolerans_m']


class TestKopruHgCapaIstasyonu:

    def test_capa_GEOMETRIK_BOGAZDAN_okunur_global_maksimumdan_degil(
            self, motor, bartz):
        """h_g makullük çapası boğaz istasyonundan okunmalı.

        Kapının kendi cümlesi "profilin tepe (BOĞAZ) değeri" diyor ve onu
        motorun BOĞAZ katsayısıyla karşılaştırıyor; karşılaştırılan
        büyüklük boğaz istasyonunun h'sidir. ``np.max(h_g)`` bunu ancak
        tepesi boğazda olan (analitik) profillerde verir. CFD profilinde
        tepe GİRİŞTEDİR (ölçüldü: 6,18 kat) ve global maks çapası geçerli
        bir profili "mertebe dışı" sayıp reddederdi.

        Bu bekçi tam o durumu kurar: boğaz değeri motorunkiyle BİREBİR
        uyuşan, ama girişte 6 katına çıkan bir profil. Çapa boğazdan
        okunuyorsa geçer; global maksimumdan okunuyorsa %518 sapmayla
        fail-closed reddedilir.
        """
        import hrma.fea.bridge as BR
        prof, z, r, hg0 = bartz
        h = np.asarray(prof['h_g'], dtype=float)
        i_bogaz = int(np.argmin(r))
        # Boğazda motorun değeri; girişe doğru 6 katına çıkan sırt.
        tt = np.linspace(0.0, 1.0, h.size)
        carpan = 1.0 + 5.0 * np.clip(
            (tt[i_bogaz] - tt) / max(tt[i_bogaz], 1e-12), 0.0, None)
        h_yeni = hg0 * carpan
        assert np.isclose(h_yeni[i_bogaz], hg0)
        assert h_yeni.max() / h_yeni[i_bogaz] > 5.0
        p = dict(prof, h_g=h_yeni.tolist())

        o = BR.extract_thermal_inputs(motor, p)
        assert o['status'] == BR.BRIDGE_STATUS_OK, (
            f"boğaz değeri motorunkiyle aynı olan profil reddedildi — çapa "
            f"global maksimumdan okunuyor olabilir: {o.get('reason')}")
        kapi = o['_basis']['h_profili']['makulluk_kapisi']
        assert kapi['durum'] == 'gecti'
        assert kapi['profil_tepe_h_g_W_m2K'] == pytest.approx(hg0, rel=1e-9)
        assert (o['_basis']['h_profili']['bogaz_h_g_istasyonu']
                == pytest.approx(i_bogaz, abs=1))

    def test_mertebe_disi_profil_HALA_reddedilir(self, motor, bartz):
        """Çapa istasyonu değişti diye makullük kapısı gevşemedi."""
        import hrma.fea.bridge as BR
        prof, z, r, hg0 = bartz
        h = np.asarray(prof['h_g'], dtype=float)
        o = BR.extract_thermal_inputs(motor, dict(prof, h_g=(h / 50.0).tolist()))
        assert o['status'] != BR.BRIDGE_STATUS_OK
        assert 'axial_profile.h_g' in ' '.join(o.get('missing') or [])


# ===========================================================================
# 3) Mesh — eğrilik tabanı inceltmeyle GERİ ALINMAZ
# ===========================================================================
def _sivi_girdi():
    from hrma.fea import bridge
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    pts_mm, _m = sample_nozzle_inner_contour({
        'chamber_diameter': 0.0825, 'throat_diameter': 0.0285,
        'exit_diameter': 0.0995})
    motor = {
        'chamber_pressure': 100.0, 'chamber_length': 150.0,
        'nozzle_contour': {
            'points': [[z / 1000.0, r / 1000.0] for z, r in pts_mm]},
        'structural_analysis': {'chamber_structure': {
            'wall_thickness': 2.0, 'wall_thickness_source': 'test sabiti',
            'material_key': 'inconel_718', 'yield_strength': 1100.0}}}
    return bridge.extract_structural_inputs(motor)


@pytest.fixture(scope='module')
def sivi():
    return _sivi_girdi()


class TestEgrilikTabaniInceltmeyeDayanikli:

    TABAN = 0.002

    @pytest.mark.parametrize('n_axial', [128, 256, 512])
    def test_taban_her_cozunurlukte_korunur(self, sivi, n_axial):
        """Mesh dış zinciri hiçbir çözünürlükte tabanın altına inmemeli.

        ÖLÇÜLDÜ (onarım ÖNCESİ, köşe penceresi ``min(2·h_loc, 4·taban)``):

            n_axial   16     32     64    128    256    512   1024
            R [mm]  12,21   9,48   4,67   3,36   2,65   1,28   0,39

        yani sayı tabana (2 mm) yakınsamıyor, SIFIRA gidiyordu: pencere
        istasyon aralığıyla orantılı olduğu için inceltme köşe düzeltmesini
        daraltıyor ve tabanı fiilen geri alıyordu. "Ne kadar incelirsen o
        kadar sivri köşe" — ters davranış.

        Pencere geometrik ölçeğe alındıktan sonra (istasyon terimi ARTIK
        ALT SINIR) ölçülen: 128 → 3,192 mm, 256 → 2,616 mm, 512 → 2,251 mm.
        Ürün akışı bu vakada n_axial = 512'ye kadar iniyor.
        """
        from hrma.fea.mesh_axisym import build_wall_mesh
        m = build_wall_mesh(sivi['contour'], sivi['thickness_m'], n_axial, 4)
        tm = m.meta['dis_yuzey_egrilik_tabani']
        assert tm['dis_egri_min_konkav_yaricap_m'] >= 0.95 * self.TABAN, (
            f'n_axial={n_axial}: dış zincir min konkav yarıçapı '
            f"{1e3 * tm['dis_egri_min_konkav_yaricap_m']:.4f} mm, taban "
            f'{1e3 * self.TABAN:.1f} mm — köşe düzeltme penceresi '
            'çözünürlükle daralıyor olabilir')

    @pytest.mark.parametrize('n_axial', [128, 256, 512])
    def test_taban_kaniti_cozunurlukten_BAGIMSIZ(self, sivi, n_axial):
        """Tabanın kanıtı kapanmış eğridedir ve n_axial'dan bağımsızdır.

        ``kapali_egri_min_konkav_yaricap_m``, yuvarlanan-top kapamasının
        ürettiği H eğrisinin n_axial'dan BAĞIMSIZ yoğun ızgaradaki (ölçüldü:
        42.171 nokta, 16.296 konkav tepe) en küçük konkav çevrel
        yarıçapıdır. Ölçülen: TAM OLARAK taban, 2,000000 mm — kapama
        öncesi ham dış eğride aynı sayı 0,0409 mm ve 13 tabanaltı köşe.

        Taban iddiası ARTIK BURADAN okunur; istasyon örneğinden değil.
        """
        from hrma.fea.mesh_axisym import build_wall_mesh
        m = build_wall_mesh(sivi['contour'], sivi['thickness_m'], n_axial, 4)
        tm = m.meta['dis_yuzey_egrilik_tabani']
        R = tm['kapali_egri_min_konkav_yaricap_m']
        assert R is not None, 'taban kanıtı yayımlanmıyor'
        assert R == pytest.approx(self.TABAN, rel=1e-6), (
            f'n_axial={n_axial}: kapanmış eğrinin min konkav yarıçapı '
            f'{1e3 * R:.6f} mm, taban {1e3 * self.TABAN:.1f} mm')

    def test_kanit_cozunurlukler_arasinda_BIT_AYNI(self, sivi):
        """Kanıt n_axial'dan bağımsızsa üç çözünürlükte de AYNI sayıdır."""
        from hrma.fea.mesh_axisym import build_wall_mesh
        degerler = []
        for na in (128, 256, 512):
            m = build_wall_mesh(sivi['contour'], sivi['thickness_m'], na, 4)
            degerler.append(
                m.meta['dis_yuzey_egrilik_tabani'][
                    'kapali_egri_min_konkav_yaricap_m'])
        assert len(set(degerler)) == 1, (
            f'taban kanıtı n_axial ile değişiyor: {degerler} — kanıt '
            "kapanmış eğriden DEĞİL mesh'in kendi zincirinden okunuyor "
            'olabilir')
