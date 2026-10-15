"""ÖH D22 — fea-cfd kulvarı, aşama 1 bekçileri.

Kalemler
--------
* **OH-D17-07** — ``/api/fea/thermal`` köprü reddinde zarf hükmü köprü
  hükmüyle tutarlı olmalı. Ölçülen kusur (taban ``b84b10a``,
  ``docs/scofield/raw/OH/D22/fea-cfd/a1/once_oh_d17_07.json``): 5/5 vakada
  (profil yok / boş profil / ``T_recovery`` eksik / ``h_g`` eksik / ortam
  sıcaklığı yok) uç HTTP 200 + üst düzey ``status='success'`` yayımlarken
  ``fea.status`` ``NOT_MODELLED`` idi — hiçbir sıcaklık alanı, hiçbir
  erime hükmü üretilmemişken zarf "başarılı" diyordu.
* **P8B1-03 / OH-D15-02** — mesh kapaması ``n_axial``'dan bağımsız değil;
  kalınlık sapması kapısı TOPLAM sapmayı ölçüyordu, dolayısıyla kapamanın
  kendi (tur-bağımsız) tabanı eşiğin üstüne çıkan geometride hiçbir tur
  kapıdan geçemiyordu ve emniyet hükmü fail-closed geri çekiliyordu.
* **P8B2-13** — hibritte kamara cidarı bütün lüle boyunca uygulandığı için
  boğazda ``t/r`` "ince cidar" öncülünü kırıyor; sınır beyanı yoktu.

Bu dosya YALNIZ bu kalemlerin bekçisidir; her biri ters-mutasyonla
kırmızıya çevrilebildiği kanıtlanmıştır
(``docs/scofield/raw/OH/D22/fea-cfd/a1/mutasyon*.json``).
"""

import contextlib
import io
import json
import pathlib

import numpy as np
import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]

#: OH-D17-07 sözleşmesi — köprünün her red durumu için (üst düzey status,
#: HTTP kodu). Tek kaynak: ``hrma/app.py`` içindeki ``_red_esleme``.
RED_SOZLESMESI = {
    'NOT_MODELLED': ('not_modelled', 422),
    'NOT_AVAILABLE': ('not_available', 501),
    'INPUTS_READY': ('inputs_ready', 501),
}

#: Redli gövdede BULUNMAMASI zorunlu alanlar (hiçbir sayı uydurulmadı).
REDDE_BULUNMAYACAK = ('fields', 'scalars', 'energy', 'time_step')


def _sessiz(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*a, **kw)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def motor(client):
    """GERÇEK ``/calculate`` hibrit sonucu (2 kN / 30 bar)."""
    # ÖH 15 Eki (ana model): ölçüm koşulu AÇIKÇA — duvar profili isteği
    # malzemeyi 'steel_4130' veriyor; HB10 hibrit kamara varsayılanını 304'e
    # çevirince köprü (doğru olarak) axial_profile_material_mismatch ile
    # reddediyordu. Motor da aynı malzemeyle kurulur; beklentiler DEĞİŞMEDİ.
    r = _sessiz(client.post, '/calculate', json={
        'thrust': 2000, 'burn_time': 10, 'of_ratio': 6.0,
        'chamber_pressure': 30.0, 'fuel_type': 'htpb',
        'oxidizer_type': 'n2o', 'chamber_material': 'steel_4130'})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()['motor']


# ===========================================================================
# OH-D17-07 — zarf hükmü ⟷ köprü hükmü
# ===========================================================================
class TestOHD1707ZarfHukmu:
    """Köprü reddederse zarf da reddeder; 'success' kazanılmadan yazılmaz."""

    #: Ölçümde kusuru üreten beş vaka (once_oh_d17_07.json ile aynı küme).
    VAKALAR = {
        'profil_yok': {'ambient_temperature_K': 300.0},
        'bos_profil': {'ambient_temperature_K': 300.0,
                       'axial_profile': {'x_mm': [], 'h_g': [],
                                         'T_recovery': []}},
        'T_recovery_eksik': {
            'ambient_temperature_K': 300.0,
            'axial_profile': {'x_mm': [0.0, 10.0, 20.0],
                              'h_g': [500.0, 600.0, 700.0]}},
        'h_g_eksik': {
            'ambient_temperature_K': 300.0,
            'axial_profile': {'x_mm': [0.0, 10.0, 20.0],
                              'T_recovery': [3000.0, 3100.0, 3200.0]}},
        'ortam_sicakligi_yok': {},
    }

    @pytest.mark.parametrize('ad', sorted(VAKALAR))
    def test_koprü_reddinde_zarf_success_demiyor(self, client, motor, ad):
        yuk = dict(self.VAKALAR[ad])
        yuk['motor_results'] = motor
        r = _sessiz(client.post, '/api/fea/thermal', json=yuk)
        govde = r.get_json()
        fea = govde.get('fea') or {}
        assert fea.get('status') in RED_SOZLESMESI, (
            f'{ad}: köprü reddi beklenirken fea.status={fea.get("status")!r}')
        ust, http = RED_SOZLESMESI[fea['status']]
        # KUSURUN KENDİSİ: zarf 'success' + 200 diyemez.
        assert govde.get('status') != 'success', (
            f'{ad}: köprü {fea["status"]} derken zarf "success" dedi — '
            'kazanılmamış hüküm yayımlandı')
        assert r.status_code != 200, (
            f'{ad}: köprü reddetti ama HTTP 200 döndü')
        assert govde.get('status') == ust, (
            f'{ad}: zarf durumu {govde.get("status")!r}, beklenen {ust!r}')
        assert r.status_code == http, (
            f'{ad}: HTTP {r.status_code}, beklenen {http}')

    @pytest.mark.parametrize('ad', sorted(VAKALAR))
    def test_redde_hicbir_sayi_uydurulmuyor(self, client, motor, ad):
        yuk = dict(self.VAKALAR[ad])
        yuk['motor_results'] = motor
        r = _sessiz(client.post, '/api/fea/thermal', json=yuk)
        fea = (r.get_json() or {}).get('fea') or {}
        for alan in REDDE_BULUNMAYACAK:
            assert alan not in fea, (
                f'{ad}: red yanıtında {alan!r} var — bir yerden sayı üretilmiş')

    @pytest.mark.parametrize('ad', sorted(VAKALAR))
    def test_reddin_gerekcesi_adiyla_soyleniyor(self, client, motor, ad):
        """Fail-closed sözleşmesi: red + ALAN ADI + gerekçe."""
        yuk = dict(self.VAKALAR[ad])
        yuk['motor_results'] = motor
        r = _sessiz(client.post, '/api/fea/thermal', json=yuk)
        govde = r.get_json()
        assert govde['missing'], f'{ad}: eksik alan adı zarfta yok'
        assert govde['missing'] == govde['fea']['missing'], (
            f'{ad}: zarf ve fea bloğu farklı eksik listesi yayımlıyor')
        assert govde['bridge_status'] == govde['fea']['status']
        assert govde['error'] == govde['status']
        assert isinstance(govde.get('message'), str) and govde['message']

    def test_gecerli_kosu_hala_success(self, client, motor):
        """Kapı yalnız reddi yakalar: kazanılmış hüküm 200 + success kalır."""
        wp = _sessiz(client.post, '/api/analysis/wall-profile', json={
            'chamber_pressure': motor['chamber_pressure'],
            'chamber_temperature': motor['chamber_temperature'],
            'chamber_diameter': motor['chamber_diameter'],
            'chamber_length': motor['chamber_length'],
            'burn_time': motor['burn_time'],
            'mdot_total': motor['mdot_total'],
            'throat_diameter': motor['throat_diameter'],
            'exit_diameter': motor['exit_diameter'],
            'expansion_ratio': motor['expansion_ratio'],
            'nozzle_type': 'conical', 'material': 'steel_4130',
            'wall_thickness': 0.005})
        assert wp.status_code == 200
        profil = wp.get_json()['wall_profile']
        r = _sessiz(client.post, '/api/fea/thermal', json={
            'motor_results': motor, 'axial_profile': profil,
            'ambient_temperature_K': 293.15,
            'n_axial': 16, 'n_radial': 3, 'max_halvings': 0})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        govde = r.get_json()
        assert govde['status'] == 'success'
        assert govde['fea']['status'] == 'ok'

    def test_panel_adli_reddi_beyan_olarak_okuyor(self):
        """Panel, adlandırılmış reddi jenerik hataya düşürmez.

        Uç 422 döndüğünde ``r.ok`` yanlıştır; panel eski hâlinde gövdeyi
        jenerik ``feaT.httpError`` metnine çeviriyordu ve kullanıcı hangi
        alanın eksik olduğunu göremiyordu. Panelin kendi NOT_MODELLED
        kartı (``buildViewModel``) bu gövdeyi göstermek için zaten var.
        """
        src = (KOK / 'hrma/static/js/thermal_fea_panel.js').read_text(
            encoding='utf-8')
        for durum in ('not_modelled', 'not_available', 'inputs_ready'):
            assert f"'{durum}'" in src, (
                f'panel {durum!r} adlı reddi tanımıyor')
        # Kararın KENDİSİ sınanır, yalnız adın geçmesi değil: adlandırılmış
        # red kümesinin ÜYELİK sınaması ve başarı dalının o sonucu kullanması.
        assert 'REDDEDILEN.indexOf(durum) >= 0' in src, (
            'panel adlandırılmış red kümesine üyelik sınamıyor — red beyanı '
            'jenerik hataya düşer')
        assert "durum === 'success' || koprununRedBeyani" in src, (
            'başarı dalı red beyanını kabul etmiyor; fea gövdesi düşürülür')
        # Eski koşul TEK BAŞINA kalmamalı: 'success' değilse hata dalı.
        assert "r.body.status !== 'success'" not in src.split(
            'koprununRedBeyani')[-1], (
            'red dalından sonra hâlâ ham "success değilse hata" koşulu var')


# ===========================================================================
# P8B1-03 / OH-D15-02 — kalınlık sapmasının AYRIŞTIRILMASI
# ===========================================================================
class TestP8B103SapmaAyristirmasi:
    """Kapı, tur-bağımsız kapama tabanını değil YERLEŞİM payını ölçer."""

    def test_meta_uc_sapmayi_da_yayimliyor(self):
        from hrma.fea.mesh_axisym import build_wall_mesh
        m = build_wall_mesh(_kontur(), 0.0158119, n_axial=32, n_radial=4)
        tb = m.meta['dis_yuzey_egrilik_tabani']
        for alan in ('kalinlik_sapma_orani',
                     'kapama_taban_sapma_orani',
                     'yerlesim_sapma_orani'):
            assert alan in tb, f'{alan} yayımlanmıyor'
            assert tb[alan] is not None, f'{alan} None'

    def test_kapama_tabani_n_axial_den_BAGIMSIZ(self):
        """Ayrıştırmanın çekirdeği: taban payı turdan tura değişmez."""
        from hrma.fea.mesh_axisym import build_wall_mesh
        tabanlar = []
        for na in (16, 32, 64, 128):
            m = build_wall_mesh(_kontur(), 0.0158119, n_axial=na, n_radial=4)
            tabanlar.append(
                m.meta['dis_yuzey_egrilik_tabani']['kapama_taban_sapma_orani'])
        yayilim = max(tabanlar) - min(tabanlar)
        assert yayilim < 1e-9, (
            'kapama taban payı n_axial ile değişiyor (yayılım %.3e): %r'
            % (yayilim, tabanlar))

    def test_yerlesim_payi_ince_turlarda_KARARLI(self):
        """Yakınsama iddiasının ölçülebilir hâli.

        Yerleşim payı sıfıra gitmek zorunda DEĞİLDİR (istasyon ızgarası
        kapanmış geometrinin tepe noktasını örneklemeyebilir; o güvenli
        yöndür). Yakınsamanın ölçülebilir hâli, payın ince turlarda
        KARARLI olmasıdır — tabanın aksine tur-bağımlı olan pay budur ve
        turdan tura zıplamamalıdır.
        """
        from hrma.fea.mesh_axisym import build_wall_mesh
        pay = {}
        for na in (256, 512, 1024):
            m = build_wall_mesh(_kontur(), 0.0158119, n_axial=na, n_radial=4)
            pay[na] = m.meta['dis_yuzey_egrilik_tabani'][
                'yerlesim_sapma_orani']
        yayilim = max(pay.values()) - min(pay.values())
        assert yayilim < 0.02, (
            f'yerleşim payı ince turlarda kararsız (yayılım {yayilim:.4f}): '
            f'{pay!r}')

    def test_kapi_YALNIZ_emniyetsiz_yonu_kesiyor(self):
        """Negatif (ince) yerleşim payı güvenli yöndür, kapı onu düşürmez."""
        from hrma.fea import structural_axisym as SA
        from hrma.fea.mesh_axisym import build_wall_mesh, AxisymMesh
        m = build_wall_mesh(_kontur(), 0.0158119, n_axial=256, n_radial=4)
        assert SA._geometri_kapisi_gecti(m) is True
        # Aynı mesh, yerleşim payı emniyetsiz yöne çevrilirse kapı DÜŞER.
        import copy
        sahte = copy.copy(m)
        sahte.meta = copy.deepcopy(m.meta)
        sahte.meta['dis_yuzey_egrilik_tabani'][
            'yerlesim_sapma_orani'] = SA.GEOMETRY_THICKNESS_TOL + 0.01
        assert isinstance(sahte, AxisymMesh)
        assert SA._geometri_kapisi_gecti(sahte) is False

    def test_kapi_YERLESIM_payini_olcuyor(self):
        """Kapı toplam sapmaya bakarsa tabanı yüksek geometride hiçbir tur
        geçemez; ölçüt yakınsama olmaktan çıkar."""
        from hrma.fea import structural_axisym as SA
        from hrma.fea.mesh_axisym import build_wall_mesh
        m = build_wall_mesh(_kontur(), 0.0158119, n_axial=256, n_radial=4)
        tb = m.meta['dis_yuzey_egrilik_tabani']
        olculen = SA._geometri_kalinlik_sapmasi(m)
        assert olculen == pytest.approx(tb['yerlesim_sapma_orani'],
                                        rel=1e-12, abs=1e-15), (
            'kapı yerleşim payını değil başka bir sayıyı okuyor: '
            f'{olculen!r} ⟷ {tb["yerlesim_sapma_orani"]!r}')
        assert olculen != pytest.approx(tb['kalinlik_sapma_orani'],
                                        rel=1e-12, abs=1e-15) or (
            tb['kapama_taban_sapma_orani'] == pytest.approx(0.0, abs=1e-12)), (
            'kapı hâlâ TOPLAM sapmayı ölçüyor')

    def test_toplam_sapma_beyanda_KALIYOR(self):
        """Ayrıştırma bir gizleme değil: toplam sapma yayımlanmaya devam."""
        from hrma.fea.mesh_axisym import build_wall_mesh
        m = build_wall_mesh(_kontur(), 0.0158119, n_axial=32, n_radial=4)
        tb = m.meta['dis_yuzey_egrilik_tabani']
        toplam = (1.0 + tb['kapama_taban_sapma_orani']) * (
            1.0 + tb['yerlesim_sapma_orani']) - 1.0
        assert tb['kalinlik_sapma_orani'] == pytest.approx(toplam, rel=1e-9), (
            'toplam sapma iki payın bileşimi değil — ayrıştırma tutarsız')

    def test_kapama_tabani_kapinin_beyaninda_gorunuyor(self):
        """Taban payı emniyetsiz yöndedir; SAKLANMAZ, kapı beyanında durur."""
        from hrma.fea import structural_axisym as SA
        from hrma.fea.mesh_axisym import build_wall_mesh
        m = build_wall_mesh(_kontur(), 0.0158119, n_axial=64, n_radial=4)
        beyan = SA._geometri_kapisi_beyani(m)
        assert beyan['kapama_taban_sapma_orani'] is not None
        assert beyan['yerlesim_sapma_orani'] is not None
        assert beyan['sapma_orani'] == beyan['yerlesim_sapma_orani']
        assert 'kapama' in beyan['_basis'] and 'yerleşim' in beyan['_basis']


def _kontur():
    """Hibrit 2 kN / 30 bar ölçeğinde yakınsak-ıraksak kontur (metre)."""
    z = np.linspace(0.0, 0.30, 61)
    r = np.empty_like(z)
    r_k, r_b, r_c = 0.050, 0.0121560, 0.075
    z_b = 0.18
    for i, zz in enumerate(z):
        if zz <= 0.12:
            r[i] = r_k
        elif zz <= z_b:
            u = (zz - 0.12) / (z_b - 0.12)
            r[i] = r_k + (r_b - r_k) * (3 * u ** 2 - 2 * u ** 3)
        else:
            u = (zz - z_b) / (0.30 - z_b)
            r[i] = r_b + (r_c - r_b) * u
    return np.stack([z, r], axis=1)


# ===========================================================================
# P8B2-13 — hibritte t/r "ince cidar" öncülü
# ===========================================================================
class TestP8B213InceCidarOnculu:
    """Kamara cidarı lüle boyunca uygulanınca boğazda t/r öncülü kırılır."""

    def test_sinir_TEK_KAYNAKTA_tanimli(self):
        """Sayı köprüde yeniden yazılmaz; yapısal katmandan gelir."""
        from hrma.analysis.structural_analysis import (
            THIN_WALL_T_OVER_R_LIMIT as KAYNAK)
        from hrma.fea import bridge as B
        assert B.THIN_WALL_T_OVER_R_LIMIT == KAYNAK
        assert 0.0 < KAYNAK < 1.0
        src = (KOK / 'hrma/fea/bridge.py').read_text(encoding='utf-8')
        assert 'THIN_WALL_T_OVER_R_LIMIT = _THIN_WALL_T_OVER_R_LIMIT' in src, (
            'köprü sınırı çıplak sayı olarak yeniden yazmış olabilir')

    def test_kalin_cidar_ORANIYLA_beyan_ediliyor(self):
        """Boğazda t/r ölçülür, sınırla kıyaslanır ve yayımlanır."""
        from hrma.fea import bridge as B
        rapor = B.thin_wall_report(
            r_inner_m=np.array([0.050, 0.0121560, 0.075]),
            thickness_m=0.015812)
        assert rapor['max_t_over_r'] == pytest.approx(
            0.015812 / 0.0121560, rel=1e-9)
        assert rapor['limit'] == B.THIN_WALL_T_OVER_R_LIMIT
        assert rapor['thin_wall_holds'] is False
        assert rapor['r_inner_at_max_m'] == pytest.approx(0.0121560, rel=1e-9)
        assert isinstance(rapor['_basis'], str) and rapor['_basis']

    def test_ince_cidar_gecerliyken_oncul_TUTUYOR(self):
        from hrma.fea import bridge as B
        rapor = B.thin_wall_report(
            r_inner_m=np.array([0.050, 0.0121560, 0.075]),
            thickness_m=0.0008)
        assert rapor['thin_wall_holds'] is True
        assert rapor['max_t_over_r'] < B.THIN_WALL_T_OVER_R_LIMIT

    def test_uyari_kanali_ARTIK_ACIK_kod_ve_sozluk_BIRLIKTE(self):
        """ÇEVRİLDİ — ÖH D31 fea-cfd a1 (OH-FT-01): borç ÖDENDİ.

        ESKİ HÂLİ bu bekçi borcun açılmadığını ölçüyordu:
        ``assert not hasattr(B, 'WARN_THIN_WALL_VIOLATED')`` ve
        ``assert 'thin_wall_violated' not in src``. Gerekçesi geçerliydi
        — o dalgada sözlük kaydı eklenemiyordu ve kayıtsız kod kullanıcıya
        HAM ANAHTAR gösterirdi. Ama Fable TOPLU denetimi (fea-cfd-01)
        borcun ADSIZ kaldığını ve hiç açılmadığını ölçtü (OH-FT-01:
        ``git grep thin_wall_violated hrma/`` = 0). Borç D31'de ödendi:
        kod + EN/TR sözlük kaydı + uç yüzeyi + panel rozeti BİRLİKTE
        eklendi, ``test_i18n_common.py`` envanteri gevşetilmeden yeşil.

        Bekçi SÖKÜLMEDİ: yönü çevrildi. Artık kodun ve sözlük kaydının
        BİRLİKTE var olduğunu ölçer — yani kayıtsız kod eklenmesi (eski
        bekçinin engellediği asıl kusur) hâlâ kırmızı verir.
        """
        from hrma.fea import bridge as B
        assert hasattr(B, 'WARN_THIN_WALL_VIOLATED'), (
            'ince cidar uyarı kodu YOK — OH-FT-01 borcu geri alınmış')
        src = (KOK / 'hrma/fea/bridge.py').read_text(encoding='utf-8')
        assert 'thin_wall_violated' in src
        sozluk = (KOK / 'hrma/static/js/i18n_common.js').read_text(
            encoding='utf-8')
        assert sozluk.count("'warn.fea.thin_wall_violated':") == 2, (
            'kod var ama sözlük kaydı eksik — kullanıcı HAM ANAHTAR görür '
            '(eski bekçinin engellediği kusur budur)')

    def test_hibrit_kosumunda_ihlal_YAYIMLANIYOR(self, client, motor):
        """Ürün ayağı: gerçek hibrit koşusunda oran beyanla çıkıyor."""
        from hrma.fea import bridge as B
        sonuc = B.run_structural_from_motor(motor)
        if sonuc.get('status') != B.BRIDGE_STATUS_OK:
            pytest.skip('bu koşuda yapısal köprü çözemedi: '
                        + str(sonuc.get('status')))
        # Köprü çözdüyse ölçüm ZORUNLUDUR — atlanamaz (mutasyon deliği).
        tw = (sonuc.get('meta') or {}).get('thin_wall')
        assert tw is not None, (
            'köprü çözdü ama ince cidar öncülü hiç ölçülmemiş: '
            + repr(sorted((sonuc.get('meta') or {}).keys())))
        assert 'max_t_over_r' in tw and tw['max_t_over_r'] > 0.0
        assert 'thin_wall_holds' in tw
        assert tw['limit'] == B.THIN_WALL_T_OVER_R_LIMIT
        # Gerçek hibrit varsayılanında öncül KIRIKTIR ve bu SAYIYLA
        # yayımlanır (ölçüldü: t/r = 1,5869 · sınır 0,10).
        assert tw['thin_wall_holds'] is False, tw
        assert tw['max_t_over_r'] > 1.0
        assert tw['outer_over_inner_at_max'] > 2.0, (
            'mesh dış yarıçapının iç yarıçapa oranı yayımlanmıyor')
        assert 'not_modelled' in (sonuc.get('meta') or {}), (
            'lüle için ayrı cidarın modellenmediği beyanı kayboldu')


def test_kanit_dosyalari_yerinde():
    """Ölçüm kanıtı depoda durur (rapor iddiaları izlenebilir olsun)."""
    d = KOK / 'docs/scofield/raw/OH/D22/fea-cfd/a1'
    for ad in ('once_oh_d17_07.json', 'sonra_oh_d17_07.json',
               'once_mesh.json', 'sonra_mesh.json'):
        p = d / ad
        assert kanit_gerekli(p).exists(), f'kanıt eksik: {p}'
        json.loads(kanit_gerekli(p).read_text(encoding='utf-8'))
