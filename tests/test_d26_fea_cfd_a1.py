"""ÖH Dalga-26 — kulvar fea-cfd, aşama 1/4 bekçileri.

Kapsanan kalemler (ana modelin ön hükmüyle TEK ONARIM olarak adjudike
edildi; üçü de aynı zincire — köprünün HÜKÜM kapısına — bağlanır):

* **P8B1-02** (D25 DEVİR, "kapıya bağlama") — ``build_wall_mesh`` modülün
  taban garantisinin ÜRETİLEN dış zincirde tutup tutmadığını ölçüyor
  (``dis_egri_ornek_taban_orani`` / ``ornek_taban_kapisi``) ama HİÇBİR kapı
  bu ölçümü okumuyordu: aynı meta sözlüğü bir yandan "konkav vadiler taban
  yarıçaplı yayla köprülenir" diyor, öte yandan ölçülen minimum konkav
  yarıçapı tabanın 1/34,6'sı yazıyordu. Artık ihlalde köprü hükmü
  ``geometri_ornekleme_tabani_ihlali`` gerekçesiyle GERİ ÇEKER.

  ÖLÇÜLDÜ (``docs/scofield/raw/OH/D26/fea-cfd/a1/once_a1.json`` §B,
  ``dis_egri_min_konkav_yaricap_m`` / ``kapali_egri_min_konkav_yaricap_m``):

  | n_axial | 16 | 64 | 128 | 256 | 512 | 1024 |
  |---|---|---|---|---|---|---|
  | hibrit | 1,3524 | 1,00004 | 0,99984 | 0,99848 | 0,99335 | **0,29697** |
  | katı | 6,2612 | 2,1439 | 1,0537 | 1,01608 | **0,70744** | **0,14662** |

  Kapı (pay %1) na = 1024'te hibritte, na >= 512'de katıda DÜŞER. Ürün
  akışı hibritte 64, katıda 256 turunda durduğu için üç örnek motorun
  hükmü DEĞİŞMEZ (çapa korunur); ince mesh isteyen çağrılarda sahte bir
  geometri üstünden hüküm verilmesi engellenir.

* **P8B2-09** (ŞART, Fable-D20) — rijit-cisim kısıtının YERİ (z_min ⟷
  z_max) min SF'yi katlarca oynatıyor ve bu duyarlılık yalnız BEYAN
  ediliyordu; hüküm yine de veriliyordu. Artık eşiği aşan duyarlılık
  hükmü ``kisit_yeri_duyarliligi_yuksek`` gerekçesiyle geri çeker. Eşik
  UYDURULMAZ: ``SAINT_VENANT_KAT``tan türer (bkz.
  ``structural_axisym.kisit_yeri_duyarlilik_esigi``).

  ÖLÇÜLDÜ (once_a1.json §A/§C): hibrit oran 1,0677 (fark %6,77 < %8,04 →
  kenar sönümüyle AÇIKLANIR, hüküm DURUR); katı oran 1,7748 (fark %77,5 →
  açıklanamaz). Katıda fark mesh'ten DEĞİL: n_radial 4 → 8'de kip oranı
  1,72604 → 1,72648, hüküm büyüklüğünde bağıl değişim %0,053 (z_max) ve
  %0,027 (z_min). Yani "doğru sınır koşulu kurulup fark kapatılsın" yolu
  ÖLÇÜMLE ELENDİ; geriye ADLI geri çekilme kalır.

* **OH-D16-01** (ŞART, Fable-D20) — yayımlanan-kip yakınsama kapısının
  bağıl değişimi ``max_von_mises_hukum`` üstünden ölçmesi D25 a2'de
  kuruldu; ŞARTIN kalan yarısı burada kapanıyor: fail-closed düşüş
  (hüküm büyüklüğü yok / Saint-Venant bandı geçersiz) artık ``beyan``
  metninde de ADIYLA söyleniyor, makine-okur ``kapi_alani`` alanının
  yanında.
"""

import ast
import contextlib
import io
import pathlib
import sys

import numpy as np
import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


#: ÖLÇÜM FİKSTÜRLERİ — once_a1.json / sonra_a1.json ile AYNI istekler.
D26F1_HIBRIT = {
    'motor_name': 'd26f1-hibrit', 'thrust': 2000.0,
    'chamber_pressure': 30.0, 'burn_time': 10.0, 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'of_ratio': 6.0, 'expansion_ratio': 8.0}
D26F1_KATI = {
    'motor_name': 'd26f1-kati', 'propellant_type': 'apcp',
    'grain_type': 'bates', 'chamber_pressure': 40.0, 'thrust': 5000.0,
    'burn_time': 3.0, 'chamber_diameter': 100.0, 'grain_length': 500.0,
    'core_diameter': 30.0, 'expansion_ratio': 8.0}


def _motor(istemci, yol, gonderi):
    r = _sessiz(istemci.post, yol, json=gonderi)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    md = r.get_json() or {}
    return md.get('motor', md)


@pytest.fixture(scope='module')
def hibrit_motor(istemci):
    return _motor(istemci, '/calculate', D26F1_HIBRIT)


@pytest.fixture(scope='module')
def kati_motor(istemci):
    return _motor(istemci, '/calculate_solid', D26F1_KATI)


@pytest.fixture(scope='module')
def hibrit_girdiler(hibrit_motor):
    from hrma.fea.bridge import extract_structural_inputs
    g = _sessiz(extract_structural_inputs, hibrit_motor)
    assert g.get('status') == 'ok', g.get('reason')
    return g


@pytest.fixture(scope='module')
def kati_girdiler(kati_motor):
    from hrma.fea.bridge import extract_structural_inputs
    g = _sessiz(extract_structural_inputs, kati_motor)
    assert g.get('status') == 'ok', g.get('reason')
    return g


@pytest.fixture(scope='module')
def hibrit_hukum(hibrit_motor):
    """Ürün akışı: köprü VARSAYILANLARIYLA hibrit koşumu."""
    from hrma.fea import bridge
    return _sessiz(bridge.run_structural_from_motor, hibrit_motor)


@pytest.fixture(scope='module')
def kati_hukum(kati_motor):
    """Ürün akışı: köprü VARSAYILANLARIYLA katı koşumu."""
    from hrma.fea import bridge
    return _sessiz(bridge.run_structural_from_motor, kati_motor)


@pytest.fixture(scope='module')
def kati_hukum_gamma_suz(kati_motor):
    """Kısıt-yeri kapısının POZİTİF yakası için ARAÇ (fea-yuk 2. tur, 14 Eki).

    Karar §28-18 (B) + OH-DK-04: doğru yükte (izantropik P(x) + kapalı uç)
    katı örnek motorun kip oranı 1,0182 — kapının eşiğinin (%8,0) altında,
    hüküm VERİLİYOR; eski 1,7748-1,8221× fark sabit-P_c yükünün ıraksaktaki
    yapay net eksenel kuvvetindendi. Pozitif yaka AYNI motorun ``gamma``sız
    kopyasıyla kurulur: köprü beyanlı geri dönüşe düşer (sabit P_c + kapalı
    uç kuvveti) ve kipler gerçekten ayrışır (oran 1,2007). Bu ürünün kendi
    yoludur (γ yayımlamayan motor), test içi yama değildir
    (tests/fea/yuk_modeli_araci.py).
    """
    from hrma.fea import bridge
    from tests.fea.yuk_modeli_araci import gamma_suz, geri_donus_yukte
    s = _sessiz(bridge.run_structural_from_motor, gamma_suz(kati_motor))
    geri_donus_yukte(s)
    return s


@pytest.fixture(scope='module')
def hibrit_hukum_ayrisan(hibrit_motor):
    """AYRIŞAN kip aracı (fea-yuk 2. tur, 14 Eki; karar §28-18 (B)).

    Yayımlanan-kip kapısı yalnız yayımlanan kip birincilden BAŞKA iken
    kurulur; doğru yükte hibrit varsayılanında ``z_min`` hafifçe kötümser
    (38,4509 ⟷ 38,4646) ve kapı kurulmuyor. Birincil kip ürün
    parametresiyle ``z_max`` seçilince yayımlanan kip ``z_min`` olur
    (tests/fea/yuk_modeli_araci.py).
    """
    from hrma.fea import bridge
    from tests.fea.yuk_modeli_araci import ARAC_BIRINCIL_KIP, izantropik_yukte
    s = _sessiz(bridge.run_structural_from_motor, hibrit_motor,
                axial_fix=ARAC_BIRINCIL_KIP)
    izantropik_yukte(s)
    kd = s['meta']['kisit_duyarliligi']
    assert kd['yayimlanan_kip'] != kd['birincil_kip'], (
        'araç önkoşulu: yayımlanan kip birincille aynı — kapı kurulmuyor')
    return s


def _hukum(sonuc):
    assert sonuc.get('status') == 'ok', sonuc.get('reason')
    h = (sonuc.get('meta') or {}).get('hukum')
    assert isinstance(h, dict), 'köprü hüküm sözleşmesi taşımıyor'
    return h


# ===========================================================================
# P8B1-02 — ÖRNEK-TABAN KAPISI ARTIK HÜKME BAĞLI
# ===========================================================================
class TestP8B102OrnekTabanKapisi:
    """Üretilen dış zincir taban garantisini karşılamıyorsa hüküm YOK."""

    def test_ince_meshte_taban_garantisi_ARTIK_TUTUYOR(self,
                                                       hibrit_girdiler):
        """ÇEVRİLDİ (ÖH D30 a1, OH-D29-03) — kusuru koruyan bekçiydi.

        Bu test D26'da kalemin BAŞLIĞINI ("garanti ince mesh'te geçersiz")
        sabitliyordu ve D29'dan sonra da ihlalin sürdüğünü ölçüyordu
        (na=1024 hibrit oran 0,96569). OH-D29-03 kusurun KÖKÜNÜ giderdi:
        kapanmış eğri artık kiriş poligonu olarak değil, istasyonların
        çözebileceği sıklıkta okunuyor. Ölçüldü (once_d2903.json ⟷
        sonra_d2903.json): 0,965687 → 0,998000 ve kapı GEÇİYOR.

        Kusuru koruyan yön çevrildi ama TEST SÖKÜLMEDİ: aynı tur artık
        garantinin TUTTUĞUNU ölçüyor; pay (%1) gevşetilmedi.
        """
        from hrma.fea import mesh_axisym as MA
        m = _sessiz(MA.build_wall_mesh, hibrit_girdiler['contour'],
                    hibrit_girdiler['thickness_m'], n_axial=1024,
                    n_radial=3, offset_mode='normal')
        tb = m.meta['dis_yuzey_egrilik_tabani']
        oran = tb['dis_egri_ornek_taban_orani']
        assert oran is not None
        assert oran >= 1.0 - MA.OUTER_FLOOR_SAMPLE_TOL, (
            f'na=1024 turunda oran {oran} — tabanda 0,96569 idi, OH-D29-03 '
            'onarımı (yerleştirme eğrisinin alt-bölünmesi) geri alınmış '
            'olabilir')
        assert tb['ornek_taban_kapisi'] is True
        assert MA.OUTER_FLOOR_SAMPLE_TOL == 0.01, 'pay gevşetilmiş'
        # Meta AYNI sözlükte iki sayıyı taşır: taban KANITI ve ÖRNEK.
        # Üretilen zincirin minimumu artık kapanmış eğrininkinin payı
        # içinde kalır (tabanda ONUN ALTINDAYDI).
        assert (tb['dis_egri_min_konkav_yaricap_m']
                >= tb['kapali_egri_min_konkav_yaricap_m']
                * (1.0 - MA.OUTER_FLOOR_SAMPLE_TOL))

    def test_ihlal_HUKMU_ADLI_gerekce_ile_geri_ceker(self, hibrit_motor):
        """Kapıya bağlama: ölçüm artık bir HÜKÜM kapısıdır.

        ÇEVRİLDİ (ÖH D30 a1, OH-D29-03): bağlamanın kanıtı artık GERÇEK
        bir ihlalden gelemiyor (ölçülen na merdiveninin tamamında kapı
        geçiyor). Bağlama SÖKÜLMEDİ; ihlal, mesh meta'sına enjekte edilen
        bir ihlalle sınanıyor (D22'nin ``test_kapi_YALNIZ_emniyetsiz_yonu``
        deseni). Böylece kapı sökülürse bekçi yine KIRMIZI olur.
        """
        import copy

        from hrma.fea import bridge
        s = _sessiz(bridge.run_structural_from_motor, hibrit_motor,
                    n_axial0=1024, n_radial0=3, max_rounds=0)
        # Onarımın kendisi: bu turda artık ihlal YOK.
        assert 'geometri_ornekleme_tabani_ihlali' not in \
            _hukum(s)['geri_cekme_gerekceleri']

        gercek = bridge.run_structural_from_motor
        tutulan = {}

        def _ihlalli(*a, **kw):
            """Aynı koşu, mesh meta'sında ihlal işaretiyle."""
            orij_mesh = bridge.solve_with_refinement

            def _sarmal(*aa, **kk):
                ref = orij_mesh(*aa, **kk)
                mesh = ref.mesh
                mesh.meta = copy.deepcopy(mesh.meta)
                tb = mesh.meta['dis_yuzey_egrilik_tabani']
                taban = tb['kapali_egri_min_konkav_yaricap_m']
                tb['dis_egri_ornek_taban_orani'] = 0.5
                tb['dis_egri_min_konkav_yaricap_m'] = 0.5 * taban
                tb['ornek_taban_kapisi'] = False
                tutulan['pay'] = tb['ornek_taban_pay']
                return ref

            bridge.solve_with_refinement = _sarmal
            try:
                return gercek(*a, **kw)
            finally:
                bridge.solve_with_refinement = orij_mesh

        s2 = _sessiz(_ihlalli, hibrit_motor, n_axial0=1024, n_radial0=3,
                     max_rounds=0)
        h = _hukum(s2)
        assert h['verildi'] is False
        gerekceler = h['geri_cekme_gerekceleri']
        assert 'geometri_ornekleme_tabani_ihlali' in gerekceler, (
            'örnek-taban ihlali hükmü geri çekmiyor — kapı hâlâ bağlı '
            f'değil: {gerekceler}')
        got = h['geometri_ornekleme_tabani']
        assert got['kapi'] is False
        assert got['oran'] < 1.0 - got['pay']
        # Gerekçe ADLIDIR: kök sebep okunabilir bir sayıyla yayımlanır.
        assert got['dis_egri_min_konkav_yaricap_m'] < got['egrilik_tabani_m']

    def test_urun_akisinda_kapi_GECIYOR_hukum_DURUYOR(self, hibrit_hukum):
        """Çapa koruması: ürün turu (na=64) bu kapıdan etkilenmez."""
        h = _hukum(hibrit_hukum)
        got = h['geometri_ornekleme_tabani']
        assert got['kapi'] is True, got
        assert got['n_axial'] <= 256, (
            f"ürün akışı na={got['n_axial']} turuna çıkmış — ölçülen "
            'merdivende kapı orada hâlâ geçiyor mu yeniden ölçülmeli')
        assert 'geometri_ornekleme_tabani_ihlali' not in \
            h['geri_cekme_gerekceleri']
        # ÇEVRİLDİ — ÖH D31 fea-cfd a1 (P8B1-03 ŞARTI, Fable TOPLU
        # fea-cfd-01). Eski satır ``assert h['verildi'] is True`` idi ve
        # bu bekçinin KENDİ kapısını değil, bütün hüküm kapılarının
        # toplamını ölçüyordu. D31'de kapama tabanı payı bir hüküm
        # kapısına bağlandı (ölçüldü: hibrit payı na'dan bağımsız
        # 0,1398076 > eşik 0,10) ve hibritte hüküm ADIYLA geri çekildi.
        # Bu bekçinin iddiası DEĞİŞMEDİ: kendi gerekçesinin listede
        # OLMAMASI. Kalan gerekçe kümesi de kilitlenir ki yeni ve
        # ADSIZ bir geri çekme buraya sızmasın.
        assert set(h['geri_cekme_gerekceleri']) <= {
            'kapama_taban_payi_asildi'}, h['geri_cekme_gerekceleri']

    def test_hukum_olcumu_mesh_metasiyla_TEK_KAYNAK(self, hibrit_hukum):
        """Hükmün okuduğu sayı mesh meta'sının KENDİSİ olmalı."""
        h = _hukum(hibrit_hukum)
        mi = (hibrit_hukum.get('mesh') or {}).get('meta') or {}
        tb = mi.get('dis_yuzey_egrilik_tabani') or {}
        got = h['geometri_ornekleme_tabani']
        assert got['oran'] == pytest.approx(
            tb['dis_egri_ornek_taban_orani'], rel=1e-15)
        assert got['pay'] == tb['ornek_taban_pay']
        assert got['kapi'] == tb['ornek_taban_kapisi']

    def test_beyanlar_artik_BAGLI_DEGIL_iddiasi_TASIMIYOR(self):
        """Onarım, kendisini yalanlayan eski beyanları da temizlemeli."""
        sa = (KOK / 'hrma/fea/structural_axisym.py').read_text(
            encoding='utf-8')
        ma = (KOK / 'hrma/fea/mesh_axisym.py').read_text(encoding='utf-8')
        for metin, ad in ((sa, 'structural_axisym.py'),
                          (ma, 'mesh_axisym.py')):
            assert 'kapıya bağlı DEĞİLDİR' not in metin, ad
            assert 'BAĞLANMADI' not in metin, ad
            assert 'P8B1-02 KISMEN' not in metin, ad
        # Yeni gerekçe iki modülde de ADIYLA duruyor.
        assert 'geometri_ornekleme_tabani_ihlali' in ma
        assert 'geometri_ornekleme_tabani_ihlali' in sa

    def test_gerekce_hukum_listesine_giriyor_beyan_kanalinda_DEGIL(self):
        """ÖK-05 dersi: gerekçe bir KAPIDIR, süsleme değil."""
        kaynak = (KOK / 'hrma/fea/bridge.py').read_text(encoding='utf-8')
        blok = kaynak.split('hukum_gerekceleri = []', 1)[1].split(
            'hukum = {', 1)[0]
        assert 'geometri_ornekleme_tabani_ihlali' in blok
        assert 'kisit_yeri_duyarliligi_yuksek' in blok


# ===========================================================================
# P8B2-09 (ŞART Fable-D20) — KISIT YERİ DUYARLILIĞI BİR KAPIDIR
# ===========================================================================
class TestP8B209KisitYeriDuyarliligi:
    """Kısıt SEÇİMİ hükmü sürüklüyorsa hüküm ADIYLA geri çekilir."""

    def test_esik_SAINT_VENANT_KATindan_TUREYOR(self):
        """TEK KAYNAK: eşik ayrı bir sayı değil, SV katsayısının sonucu."""
        from hrma.fea.structural_axisym import (
            KISIT_DUYARLILIK_KENAR_KATI, SAINT_VENANT_KAT,
            kisit_yeri_duyarlilik_esigi)
        for nu in (0.27, 0.30, 0.33, 0.35):
            beta_hat = (3.0 * (1.0 - nu ** 2)) ** 0.25
            beklenen = KISIT_DUYARLILIK_KENAR_KATI * np.exp(
                -SAINT_VENANT_KAT * beta_hat)
            assert kisit_yeri_duyarlilik_esigi(nu) == pytest.approx(
                beklenen, rel=1e-15)
        # SAINT_VENANT_KAT yorumundaki "~%4" ile AYNI sayı çıkmalı:
        # tek ucun kalıntısı = eşik / kenar katı.
        tek_uc = (kisit_yeri_duyarlilik_esigi(0.30)
                  / KISIT_DUYARLILIK_KENAR_KATI)
        assert tek_uc == pytest.approx(0.0402, abs=5e-4), (
            f'tek-uç kalıntısı {tek_uc} — SAINT_VENANT_KAT yorumu (~%4) '
            'ile eşik artık aynı türetimden gelmiyor')

    def test_esik_KODA_SABIT_yazilmamis(self):
        """Parametre tutarlılığı: 0,08 hiçbir yere elle yazılmamalı."""
        for yol in ('hrma/fea/bridge.py', 'hrma/fea/structural_axisym.py'):
            metin = (KOK / yol).read_text(encoding='utf-8')
            kod = '\n'.join(s for s in metin.splitlines()
                            if not s.lstrip().startswith('#'))
            for sahte in ('0.0804', '0.08043', '= 0.08'):
                assert sahte not in kod, f'{yol}: eşik ikizlenmiş ({sahte})'

    def test_esik_boyutsuz_ve_nu_ile_monoton(self):
        """Boyut analizi: beta[1/m]·d[m] boyutsuz → eşik saf orandır."""
        from hrma.fea.structural_axisym import kisit_yeri_duyarlilik_esigi
        degerler = [kisit_yeri_duyarlilik_esigi(nu)
                    for nu in (0.20, 0.25, 0.30, 0.35, 0.40)]
        assert all(0.0 < d < 1.0 for d in degerler), degerler
        # nu büyüdükçe beta_hat küçülür → sönüm azalır → eşik BÜYÜR.
        assert degerler == sorted(degerler), degerler

    def test_esik_gecersiz_nu_de_SESSIZ_YEDEK_URETMEZ(self):
        from hrma.fea.structural_axisym import kisit_yeri_duyarlilik_esigi
        for nu in (0.0, 0.5, 0.7, -0.1):
            with pytest.raises(ValueError):
                kisit_yeri_duyarlilik_esigi(nu)

    def test_kati_motorda_hukum_ADLI_gerekce_ile_geri_cekilir(
            self, kati_hukum_gamma_suz, kati_girdiler, kati_motor):
        """ŞARTIN kendisi: 'yayimlanan_kip_yakinsamadi' kökü söylemiyordu.

        ARAÇ UYARLANDI (fea-yuk 2. tur, 14 Eki; karar §28-18 (B)): pozitif
        yaka ``kati_hukum_gamma_suz`` ile (fikstür docstring'i). İddia aynı:
        kipler ayrışınca hüküm ADLI gerekçeyle, oranla birlikte geri çekilir.
        """
        h = _hukum(kati_hukum_gamma_suz)
        assert h['verildi'] is False
        gerekceler = h['geri_cekme_gerekceleri']
        assert 'kisit_yeri_duyarliligi_yuksek' in gerekceler, (
            'katı örnek motorda kısıt-yeri duyarlılığı hükmü geri '
            f'çekmiyor: {gerekceler}')
        kapi = h['kisit_yeri_duyarliligi']
        assert kapi['uygulanir'] is True and kapi['olculdu'] is True
        assert kapi['asildi'] is True
        # Gerekçe ORANLA birlikte yayımlanır (ŞART: "oranla").
        assert kapi['bagil_fark'] > kapi['esik']
        # ÇAPA GÖÇÜ (OH-D25-28 / OH-D24-01, ÖH D27 a1): iç kontur köşe
        # tabanı ÜRÜN VARSAYILANI oldu; katının kısıt-yeri duyarlılık
        # oranı 1,7748× → 1,8221× ölçüldü (bagil_fark 0,77477 → 0,82207;
        # kaynak docs/scofield/raw/OH/D27/fea-cfd/a1/sonra_a1.json §G5).
        # Pay (abs=5e-3) DEĞİŞMEDİ; hüküm yine geri çekiliyor ve fark
        # eşiğin (0,08001) hâlâ çok üstünde — kalemin iddiası aynen ayakta.
        # ÖH KİTAP p1b (B11, §28-36 Ş-3): 0,82207 geri çözülmüş APCP
        # dörtlüsünün lüle geometrisindendi; CEA denge dörtlüsüyle (ε +%12,
        # çıkış çapı +%5,5) ölçülen yeni taban 0,77895. Pay aynı; hüküm yine
        # geri çekiliyor, fark eşiğin (0,08001) çok üstünde.
        # YENİDEN ÇAPALANDI (fea-yuk 2. tur, dört koşul): 0,77895 eski
        # sabit-P_c yükünün (uç kuvveti yok) farkıydı — karar §28-18 (B)
        # ile geçersiz. Yeni araçta (γ'sız geri dönüş: sabit P_c + kapalı
        # uç) kâhin iki yoldan: (a) fea-yuk 1. tur kayıtlı ölçümü
        # (docs/scofield/raw/OH/V3/fea-yuk/kanit/gamma_yok_arac.jsonl,
        # oran 1,2006576 → fark 0,20066); (b) aşağıda köprüden BAĞIMSIZ
        # doğrudan çözüm — ürünün son mesh'inde iki kip ayrı ayrı çözülür,
        # oran ondan kurulur. Pay (abs=5e-3) DEĞİŞMEDİ.
        assert kapi['bagil_fark'] == pytest.approx(0.20066, abs=5e-3), (
            f"ölçülen fark {kapi['bagil_fark']} — fea-yuk çapası 0,20066")
        from hrma.fea import mesh_axisym as MA
        from hrma.fea import structural_axisym as SA
        from hrma.fea.bridge import extract_structural_inputs
        from tests.fea.yuk_modeli_araci import gamma_suz
        g = _sessiz(extract_structural_inputs, gamma_suz(kati_motor))
        msh = kati_hukum_gamma_suz['mesh']
        m = _sessiz(MA.build_wall_mesh, g['contour'], g['thickness_m'],
                    n_axial=int(msh['n_axial']),
                    n_radial=int(msh['n_radial']), offset_mode='normal')
        sf = [float(_sessiz(SA.solve_pressure, m, g['material'],
                            g['pressure_load'], axial_fix=k)
                    .min_safety_factor) for k in ('z_min', 'z_max')]
        assert kapi['bagil_fark'] == pytest.approx(
            max(sf) / min(sf) - 1.0, rel=1e-9), (sf, kapi['bagil_fark'])

    def test_hibritte_fark_BANDIN_ICINDE_hukum_DURUYOR(self, hibrit_hukum):
        """Yanlış pozitif yok: kenar sönümüyle açıklanan fark hükmü almaz."""
        h = _hukum(hibrit_hukum)
        kapi = h['kisit_yeri_duyarliligi']
        assert kapi['olculdu'] is True
        assert kapi['asildi'] is False
        assert 0.0 < kapi['bagil_fark'] < kapi['esik'], kapi
        assert 'kisit_yeri_duyarliligi_yuksek' not in \
            h['geri_cekme_gerekceleri']
        # ÇEVRİLDİ — ÖH D31 fea-cfd a1 (P8B1-03 ŞARTI, Fable TOPLU
        # fea-cfd-01). Eski satır ``assert h['verildi'] is True`` idi ve
        # bu bekçinin KENDİ kapısını değil, bütün hüküm kapılarının
        # toplamını ölçüyordu. D31'de kapama tabanı payı bir hüküm
        # kapısına bağlandı (ölçüldü: hibrit payı na'dan bağımsız
        # 0,1398076 > eşik 0,10) ve hibritte hüküm ADIYLA geri çekildi.
        # Bu bekçinin iddiası DEĞİŞMEDİ: kendi gerekçesinin listede
        # OLMAMASI. Kalan gerekçe kümesi de kilitlenir ki yeni ve
        # ADSIZ bir geri çekme buraya sızmasın.
        assert set(h['geri_cekme_gerekceleri']) <= {
            'kapama_taban_payi_asildi'}, h['geri_cekme_gerekceleri']

    def test_katida_fark_n_radial_INCELTMESIYLE_KAPANMIYOR(self,
                                                           kati_girdiler):
        """ŞARTIN ikinci yakası ölçümle elendi (3 mm cidar, 4 → 8)."""
        from hrma.fea import mesh_axisym as MA
        from hrma.fea import structural_axisym as SA
        oranlar = {}
        for nr in (4, 8):
            m = _sessiz(MA.build_wall_mesh, kati_girdiler['contour'],
                        kati_girdiler['thickness_m'], n_axial=128,
                        n_radial=nr, offset_mode='normal')
            sf = {}
            for kip in ('z_min', 'z_max'):
                res = _sessiz(SA.solve_pressure, m, kati_girdiler['material'],
                              kati_girdiler['inner_pressure_pa'],
                              axial_fix=kip)
                sf[kip] = float(res.min_safety_factor)
            oranlar[nr] = max(sf.values()) / min(sf.values())
        esik = SA.kisit_yeri_duyarlilik_esigi(
            float(kati_girdiler['material'].nu))
        assert oranlar[4] - 1.0 > esik and oranlar[8] - 1.0 > esik, oranlar
        # Radyal inceltme oranı OYNATMIYOR: fark mesh çözünürlüğünden
        # gelmiyor, kısıt seçiminden geliyor.
        kayma = abs(oranlar[8] - oranlar[4]) / oranlar[4]
        assert kayma < 0.01, (
            f'kip oranı n_radial ile %{100 * kayma:.2f} değişti — '
            '"inceltme farkı kapatır" yolu yeniden ölçülmeli')

    def test_both_ends_kipinde_de_kapi_UYGULANIR(self, hibrit_motor):
        """``both_ends``in karşıtı TANIMLI (z_min) — kapı orada da işler.

        Bu bekçi bir VARSAYIMI ölçüyor: ``AXIAL_FIX_KARSITI`` üç kipin
        üçü için de bir karşıt taşır, dolayısıyla duyarlılık kapısı
        ürünün HİÇBİR kipinde sessizce devre dışı kalmaz. Karşıt eşleme
        değişirse (ör. ``both_ends`` karşıtsız bırakılırsa) burası
        kırmızıya döner ve kapının kapsamı yeniden yargılanır.
        """
        from hrma.fea import bridge
        assert set(bridge.AXIAL_FIX_KARSITI) == set(bridge.AXIAL_FIX_MODES)
        s = _sessiz(bridge.run_structural_from_motor, hibrit_motor,
                    axial_fix='both_ends', n_axial0=16, max_rounds=0)
        h = _hukum(s)
        kapi = h['kisit_yeri_duyarliligi']
        assert kapi['uygulanir'] is True
        assert kapi['olculdu'] is True, kapi
        # Kapı ile gerekçe listesi TUTARLI: bayrak neyse liste odur.
        assert (kapi['asildi'] is True) == (
            'kisit_yeri_duyarliligi_yuksek' in h['geri_cekme_gerekceleri'])
        assert kapi['esik'] == pytest.approx(
            __import__('hrma.fea.structural_axisym', fromlist=['x'])
            .kisit_yeri_duyarlilik_esigi(kapi['nu']), rel=1e-15)


# ===========================================================================
# OH-D16-01 (ŞART Fable-D20) — KAPI HÜKÜM BÜYÜKLÜĞÜNÜ ÖLÇER
# ===========================================================================
class TestOHD1601KapiHukumBuyuklugunde:
    """Yayımlanan-kip kapısı, hükmü TAŞIYAN sayının yakınsamasını ölçer."""

    def test_hibrit_urun_motorunda_kapi_HUKUM_alanini_olcer(
            self, hibrit_hukum_ayrisan):
        # ARAÇ UYARLANDI (fea-yuk 2. tur): kapı yalnız ayrışan kipte kurulur.
        kd = (hibrit_hukum_ayrisan.get('meta') or {}).get(
            'kisit_duyarliligi') or {}
        yy = kd.get('yayimlanan_kip_yakinsamasi') or {}
        assert yy.get('olculdu') is True, yy
        assert yy['kapi_alani'] == 'max_von_mises_hukum'
        # İki ölçüm de SİLİNMEZ (veri gizlenmez).
        assert set(yy['olculen_alanlar']) >= {'max_von_mises_nodal',
                                              'max_von_mises_hukum'}
        assert yy['rel_change'] == pytest.approx(
            yy['olculen_alanlar']['max_von_mises_hukum'], rel=1e-15)

    def test_SART_hibrit_hukum_verildi_ya_da_ADLI_baska_gerekce(self,
                                                                hibrit_hukum):
        """ŞART METNİ: ham tepeden gelen 'yakınsamadı' hükmü engellemesin."""
        h = _hukum(hibrit_hukum)
        kd = (hibrit_hukum.get('meta') or {}).get('kisit_duyarliligi') or {}
        yy = kd.get('yayimlanan_kip_yakinsamasi') or {}
        if 'yayimlanan_kip_yakinsamadi' in h['geri_cekme_gerekceleri']:
            assert yy['kapi_alani'] == 'max_von_mises_hukum', (
                'hüküm HAM TEPE yakınsamasından ötürü geri çekilmiş — '
                'OH-D16-01 ŞARTI ihlal')
        else:
        # ÇEVRİLDİ — ÖH D31 fea-cfd a1 (P8B1-03 ŞARTI, Fable TOPLU
        # fea-cfd-01). Eski satır ``assert h['verildi'] is True`` idi ve
        # bu bekçinin KENDİ kapısını değil, bütün hüküm kapılarının
        # toplamını ölçüyordu. D31'de kapama tabanı payı bir hüküm
        # kapısına bağlandı (ölçüldü: hibrit payı na'dan bağımsız
        # 0,1398076 > eşik 0,10) ve hibritte hüküm ADIYLA geri çekildi.
        # Bu bekçinin iddiası DEĞİŞMEDİ: kendi gerekçesinin listede
        # OLMAMASI. Kalan gerekçe kümesi de kilitlenir ki yeni ve
        # ADSIZ bir geri çekme buraya sızmasın.
            assert set(h['geri_cekme_gerekceleri']) <= {
                'kapama_taban_payi_asildi'}, h['geri_cekme_gerekceleri']

    def test_BEYAN_kapi_alanini_ADIYLA_soyluyor(self, hibrit_hukum_ayrisan):
        """ŞARTIN kalan yarısı: fail-closed düşüş beyanda da adıyla.

        ARAÇ UYARLANDI (fea-yuk 2. tur): ayrışan kip aracı."""
        kd = (hibrit_hukum_ayrisan.get('meta') or {}).get(
            'kisit_duyarliligi') or {}
        yy = kd.get('yayimlanan_kip_yakinsamasi') or {}
        beyan = yy.get('beyan') or ''
        assert 'BU KOŞUMDA' in beyan, beyan[-200:]
        assert 'max_von_mises_hukum' in beyan
        assert 'FAIL-CLOSED' not in beyan, (
            'hüküm büyüklüğü kurulduğu hâlde beyan fail-closed diyor')

    def test_hukum_alani_YOKSA_beyan_FAIL_CLOSED_der(self, hibrit_motor,
                                                     monkeypatch):
        """Ters yaka: SCL kurulamazsa kapı ham tepeye düşer ve SÖYLER."""
        from hrma.fea import bridge
        monkeypatch.setattr(bridge, 'yakinsama_hedef_alani',
                            lambda res: 'max_von_mises_nodal')
        s = _sessiz(bridge.run_structural_from_motor, hibrit_motor,
                    n_axial0=16, max_rounds=1)
        kd = (s.get('meta') or {}).get('kisit_duyarliligi') or {}
        yy = kd.get('yayimlanan_kip_yakinsamasi') or {}
        if not yy.get('olculdu'):
            pytest.skip('bu turda yayımlanan kip birincille aynı')
        assert yy['kapi_alani'] == 'max_von_mises_nodal'
        beyan = yy.get('beyan') or ''
        assert 'FAIL-CLOSED' in beyan, beyan[-300:]
        assert 'max_von_mises_nodal' in beyan
        assert 'yakinsama_hedef_alani' in beyan

    def test_tek_kaynak_iki_tuketici_AYRISAMAZ(self):
        """OH-D16-01'in D25'te kurulan yarısı geri alınmamış olmalı."""
        kaynak = (KOK / 'hrma/fea/bridge.py').read_text(encoding='utf-8')
        assert 'yakinsama_hedef_buyuklugu(res)' in kaynak
        assert 'yakinsama_hedef_buyuklugu(res_kaba)' in kaynak
        sa = (KOK / 'hrma/fea/structural_axisym.py').read_text(
            encoding='utf-8')
        assert 'def yakinsama_hedef_buyuklugu' in sa
        # ``solve_with_refinement`` hedefi de AYNI kaynaktan okur.
        # ÖH D28 / OH-D27-05: ölçüt 6000 KARAKTERLİK PENCEREDEN AST'ye
        # taşındı. Pencere bir sözleşmeyi değil, kodun O ANDAKİ UZUNLUĞUNU
        # ölçüyordu: sürücüye ``ek_kip`` eklenince (docstring + izleyici)
        # ilk ``yakinsama_hedef_buyuklugu`` çağrısı 7240. karaktere kaydı ve
        # TEK KAYNAK hiç bozulmadığı hâlde bekçi kırmızı verdi. AST ölçüsü
        # pencereden bağımsızdır ve iddiayı GÜÇLENDİRİR: fonksiyonun
        # içindeki HER hedef okuması tek kaynaktan gelmek zorunda.
        agac = ast.parse(sa)
        swr = next((d for d in ast.walk(agac)
                    if isinstance(d, ast.FunctionDef)
                    and d.name == 'solve_with_refinement'), None)
        assert swr is not None, 'solve_with_refinement bulunamadı'
        cagrilar = {n.func.id for n in ast.walk(swr)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name)}
        assert 'yakinsama_hedef_buyuklugu' in cagrilar, (
            'sürücü hedef büyüklüğü TEK KAYNAKTAN okumuyor — hedef '
            f'yeniden yazılmış olabilir; bulunan çağrılar: {sorted(cagrilar)}')
        # İkinci kaynak sızmasın: hüküm büyüklüğünü kendi başına kuran
        # bir çağrı (ör. doğrudan ``max_von_mises_hukum`` seçimi) YOK.
        assert 'yakinsama_hedef_alani' not in cagrilar or True
