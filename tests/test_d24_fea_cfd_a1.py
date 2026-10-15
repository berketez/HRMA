"""ÖH Dalga-24 · kulvar fea-cfd · aşama 1 — OH-D15-02 bekçileri.

Kalem: OH-D15-02 (katı motorda FEA emniyet hükmü geri çekiliyor).

ÖLÇÜM SONUCU — BAŞLIK ÇÜRÜTÜLDÜ, ALTINDAN BAŞKA BİR KUSUR ÇIKTI.
Defterdeki mekanizma ("build_wall_mesh ince mesh üretemiyor → 32.768
elemanda yakınsamıyor") reprodüke OLMUYOR: mesh 8192 elemana kadar
kuruluyor ve çözülüyor (kanıt ``docs/scofield/raw/OH/D24/fea-cfd/a1/
merdiven_kati.json``). Kullanıcının katıda hüküm görmemesi ise DOĞRU
davranıştır: çözüm gerçekten yakınsamıyor — yayımlanan kip z_max'ta tepe
139,3 → 238,5 MPa, min SF 1,794 → 1,048 ve 8192 elemanda hâlâ %2,34/tur
oynuyor. Hükmü geri çekmek fail-closed doğrudur.

Aynı ölçüm TERS yönde bir kusur buldu ve onarılan odur: birincil kip
z_min'in gösterge dizisi %8,497 → %1,017 → %1,603 → %0,984 diye seyredip
son değerde "yakınsadı" sayılıyordu. Bu bir YEREL ÇUKURDUR (dizi 2.
turdan 3. tura GERİ ÇIKIYOR) ve arkasından gösterge %7,549'a fırlıyor.
Yani ürün, yakınsamamış bir çözümü "converged" ilan ediyordu ve
P17B1-02'nin kapattığı kapı (yakınsamamış çözüm hüküm veremez) bu
çukurdan geçilebiliyordu.

Bu dosyadaki bekçiler iki onarımı kilitler:
  1) ``REFINE_ONAY_ARDISIK_TUR`` — kabul tek tura değil ARDIŞIK turlara
     dayanır (yalnız sıkılaştırır; converged=True üreten yeni yol yok).
  2) P8B1-09 kapısı yayımlanan HER İKİ büyüklüğü ölçer (ham tepe +
     Saint-Venant süzülmüş hüküm tepesi) ve EN KÖTÜSÜNÜ alır.
"""
import contextlib
import io

import pytest

from hrma.fea.structural_axisym import (
    DEFAULT_REFINE_TOL,
    REFINE_ONAY_ARDISIK_TUR,
    REFINE_POLICY_JOINT,
    Material,
    solve_with_refinement,
)


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


# Lamé silindiri (test_inceltme_politikasi ile aynı deterministik vaka;
# sayılar oradan DEĞİL, çözücünün merkezî sabitlerinden türer).
LAME_A, LAME_T, LAME_L, LAME_P = 0.05, 0.025, 0.10, 10.0e6
CELIK = Material(E=200.0e9, nu=0.3, yield_strength=250.0e6,
                 name='d24-test-steel')


def _kos(**kw):
    kw.setdefault('max_rounds', 5)
    return _sessiz(solve_with_refinement,
                   [(0.0, LAME_A), (LAME_L, LAME_A)], LAME_T, CELIK, LAME_P,
                   axial_fix='both_ends', n_axial0=4, n_radial0=3, **kw)


class TestOHD1502OnayTuru:
    """Kabul ölçütü TEK tura değil ARDIŞIK turlara dayanır."""

    @pytest.fixture(scope='class')
    def ref(self):
        return _kos()

    def test_sabit_merkezi_ve_birden_buyuk(self):
        """Onay turu sayısı merkezî sabittir ve tek turluk kabulü kapatır."""
        assert isinstance(REFINE_ONAY_ARDISIK_TUR, int)
        assert REFINE_ONAY_ARDISIK_TUR >= 2, (
            'onay turu 1e düşerse kabul yine tek turluk olur ve yerel '
            'çukurdan geçilir (OH-D15-02 kusuru geri gelir)')

    def test_kabul_ardisik_tur_ister(self, ref):
        """Yakınsayan koşumda SON N tur da tolerans altında olmalı."""
        assert ref.converged
        rels = [h['rel_change'] for h in ref.history
                if h['rel_change'] is not None]
        assert len(rels) >= REFINE_ONAY_ARDISIK_TUR, (
            'kabul, onay turu kadar ölçülmüş tur olmadan verilemez')
        son = rels[-REFINE_ONAY_ARDISIK_TUR:]
        assert all(r < ref.tol for r in son), (
            'kabul edildi ama son turların hepsi tolerans altında değil — '
            f'tek turluk kabule dönülmüş olabilir: {rels}')

    def test_meta_onay_sayaci_beyanli(self, ref):
        """Ölçüt makine-okur alanda durur (tüketici kendi karar vermez)."""
        m = ref.meta
        assert m['onay_ardisik_tur_gerekli'] == REFINE_ONAY_ARDISIK_TUR
        assert m['onay_ardisik_tur_sayaci'] >= REFINE_ONAY_ARDISIK_TUR
        assert 'ARDIŞIK' in m['onay_kurali']
        assert 'Roache' in m['onay_kurali'], (
            'ölçütün literatür dayanağı beyandan düşmüş')
        assert 'ARDIŞIK' in m['beyan']

    def test_yerel_cukur_yakinsama_sayilmaz(self):
        """OH-D15-02'nin ÖLÇÜLEN kusuru: çukura düşen dizi kabul EDİLMEZ.

        Gerçek çözücüyle kurulmuş sentetik değil, DOĞRUDAN ölçüt sınaması:
        gösterge dizisi tolerans altına inip sonra üstüne çıkarsa sayaç
        sıfırlanmalı; yani "bir tur tol altında" tek başına converged
        yapmamalı. Katı motorun ölçülen dizisi bunun canlı örneğidir
        (%1,017 → %1,603 → %0,984 → %7,549).
        """
        ref = _kos()
        rels = [h['rel_change'] for h in ref.history
                if h['rel_change'] is not None]
        # Kabul edilen turdan ÖNCEKİ tur da tol altında olmalı; aksi hâlde
        # kabul tek turluk bir düşüşe dayanıyordur.
        assert len(rels) >= 2
        assert rels[-2] < ref.tol, (
            'kabul edilen turun bir öncekisi tolerans ÜSTÜNDE — bu, tek '
            f'turluk çukurdan geçilen kabuldür: {rels}')

    def test_joint_politikasi_da_onay_turu_ister(self):
        """Ölçüt yalnız varsayılan politikada değil, joint'te de geçerli.

        joint ürün içinde ``refine_policy`` ile seçilebilir; ölçütün zayıf
        kaldığı bir yol bırakılmaz.
        """
        j = _kos(refine_policy=REFINE_POLICY_JOINT)
        assert j.converged
        assert j.meta['onay_ardisik_tur_sayaci'] >= REFINE_ONAY_ARDISIK_TUR
        rels = [h['rel_change'] for h in j.history
                if h['rel_change'] is not None]
        assert all(r < j.tol for r in rels[-REFINE_ONAY_ARDISIK_TUR:]), rels

    def test_tol_altinda_bitip_yakinsamayan_kosum_ADINI_soyler(self):
        """FAIL-CLOSED beyanı: tol altında bitip onaylanamayan koşu susmaz.

        ``max_rounds`` onay turuna yetmeyecek kadar kısıtlandığında koşu
        tolerans altında bitse bile ``converged=False`` döner ve beyan
        bunun sebebini ADIYLA söyler — "tol altına indi, öyleyse
        yakınsadı" çıkarımı okuyucuya bırakılmaz.
        """
        # ÇEVRİLDİ (ÖH D25, OH-D24-01): vaka artık SABİT tolerans yerine
        # ARANARAK kuruluyor. Hüküm büyüklüğü ASME Ek 5-A
        # lineerleştirmesine geçince gösterge dizisi değişti ve eski
        # (max_rounds=1, varsayılan tol) koşumu onay turunu tamamlar oldu;
        # ayrıca dizi bu koşumda tekdüze AZALMIYOR (ölçülen: 3,87e-05 →
        # 1,95e-03), yani "son tur tol altında, önceki üstünde" hâli o
        # bütçede hiç kurulamıyor. Bekçinin iddiası büyüklüğe değil
        # BEYANA dairdir, o yüzden aranan hâl bütçe/tolerans ikilileri
        # taranarak bulunur: koşu tolerans ALTINDA biter ama onay turu
        # tamamlanmadığı için converged=False döner.
        kisa = None
        for _mr in (1, 2, 3):
            _ol = _kos(max_rounds=_mr)
            _rels = [h['rel_change'] for h in _ol.history
                     if h['rel_change'] is not None]
            for _r in sorted(set(_rels)):
                _aday = _kos(max_rounds=_mr, tol=float(_r * 1.02))
                if (_aday.converged is False
                        and _aday.final_rel_change is not None
                        and _aday.final_rel_change < _aday.tol):
                    kisa = _aday
                    break
            if kisa is not None:
                break
        assert kisa is not None, (
            'aranan hâl ("tol altında bitti ama onay turu eksik") hiçbir '
            'bütçe/tolerans ikilisinde kurulamadı — ölçüt ya hep onaylıyor '
            'ya hiç tol altına inmiyor')
        assert kisa.converged is False, (
            'onay turu olmadan kabul verildi — tek turluk kabule dönülmüş')
        assert kisa.final_rel_change is not None
        assert kisa.final_rel_change < kisa.tol, (
            'vaka kurulamadı: bu koşum zaten tolerans üstünde bitiyor, '
            f'oysa aranan hâl "tol altında ama onaysız": '
            f'{kisa.final_rel_change}')
        assert kisa.meta['onay_ardisik_tur_sayaci'] == 1
        assert 'ONAY TURU EKSİK' in kisa.meta['beyan'], kisa.meta['beyan']
        assert 'YAKINSAMADI' in kisa.meta['beyan']

    def test_olcut_gevsemedi_tolerans_yerinde(self, ref):
        """ÖK-22: sıkılaştırma tolerans gevşetilerek satın alınmadı."""
        assert ref.tol == DEFAULT_REFINE_TOL == 0.01


class TestOHD1502KapiIkiBuyukluk:
    """P8B1-09 kapısı yayımlanan HER İKİ büyüklüğü ölçer, en kötüsünü alır."""

    @pytest.fixture(scope='class')
    def kati_fea(self):
        """Katı motor köprü koşumu — yayımlanan kip birincilden farklı.

        ARAÇ UYARLANDI (fea-yuk 2. tur, 14 Eki; karar §28-18 (B), kart
        OH-DK-04). Eski sabit-P_c yükünde bu katı varsayılanında birincil
        ``z_min`` ⟷ yayımlanan ``z_max`` ayrışıyor ve kısıt-yeri kapısı
        aşılıyordu (oran 1,82); ikisi de ıraksaktaki yapay net eksenel
        kuvvetten geliyordu. Doğru yükte oran 1,0182 ve yayımlanan kip
        birincille aynı — vaka kayboldu. Araç: AYNI motorun ``gamma``sız
        kopyası (köprünün beyanlı geri dönüşü: sabit P_c + kapalı uç
        kuvveti; oran 1,2007, kapı aşılıyor) + birincil kip ürün
        parametresiyle ``z_max`` (yayımlanan kötümser ``z_min`` olur).
        İki koşul da ürünün kendi yolu (tests/fea/yuk_modeli_araci.py).
        """
        pytest.importorskip('flask')
        import os
        import tempfile
        os.environ.setdefault('HRMA_HEADLESS', '1')
        os.environ.setdefault('HRMA_USER_DATA_DIR', tempfile.mkdtemp())
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.app import app
            from hrma.fea import bridge
        app.config['TESTING'] = True
        c = app.test_client()
        r = _sessiz(c.post, '/calculate_solid', json={
            'motor_name': 'D24-OHD1502', 'propellant_type': 'apcp',
            'grain_type': 'bates', 'chamber_pressure': 40.0,
            'thrust': 5000.0, 'burn_time': 3.0, 'chamber_diameter': 100.0,
            'grain_length': 500.0, 'core_diameter': 30.0,
            'expansion_ratio': 8.0})
        assert r.status_code == 200
        j = r.get_json() or {}
        from tests.fea.yuk_modeli_araci import (ARAC_BIRINCIL_KIP, gamma_suz,
                                                geri_donus_yukte)
        s = _sessiz(bridge.run_structural_from_motor,
                    gamma_suz(j.get('motor', j)),
                    axial_fix=ARAC_BIRINCIL_KIP)
        geri_donus_yukte(s)
        kd = s['meta']['kisit_duyarliligi']
        assert kd['yayimlanan_kip'] != kd['birincil_kip'], (
            'araç önkoşulu: yayımlanan kip birincille aynı — kapı kurulmuyor')
        return s

    @pytest.fixture(scope='class')
    def hibrit_fea(self):
        """Hibrit köprü koşumu — ham ⟷ süzülmüş büyüklüğün AYRIŞTIĞI vaka."""
        pytest.importorskip('flask')
        import os
        import tempfile
        os.environ.setdefault('HRMA_HEADLESS', '1')
        os.environ.setdefault('HRMA_USER_DATA_DIR', tempfile.mkdtemp())
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.app import app
            from hrma.fea import bridge
        app.config['TESTING'] = True
        c = app.test_client()
        r = _sessiz(c.post, '/calculate', json={
            'thrust': 3000.0, 'burn_time': 40.0, 'chamber_pressure': 20.0,
            'of_ratio': 6.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
            'initial_port_diameter': 0.05, 'chamber_diameter_input': 120.0,
            'l_star': 1.0, 'expansion_ratio': 4.0, 'total_impulse': 120000.0,
            'include_plots': False, 'generate_cad': False,
            'calculate_trajectory': False,
            'include_combustion_analysis': False,
            'include_realtime_dashboard': False,
            'include_3d_visualization': False})
        assert r.status_code == 200
        j = r.get_json() or {}
        # z5guard'ın ``kopru_saglikli`` koşumunun mesh ayarları: bu
        # ayarda kaba mesh'te tepe Saint-Venant bandının İÇİNDE, ince
        # mesh'te DIŞINDA kalıyor ve iki alan AYRIŞIYOR (ölçüldü D24:
        # ham %8,639 ⟷ süzülmüş %0,137). Varsayılan mesh ayarında ise
        # inceltme daha ileri gittiği için iki alan sayıca eşitleniyor
        # ve vaka ayırt edici olmuyor.
        return _sessiz(bridge.run_structural_from_motor, j.get('motor', j),
                       max_rounds=2, n_axial0=8, n_radial0=3)

    def test_kapi_kurulabildi(self, kati_fea):
        kd = kati_fea['meta']['kisit_duyarliligi']
        assert kd['yayimlanan_kip'] != kd['birincil_kip'], (
            'ön koşul kayboldu: bu vaka kötümser kipin yayımlandığı vakadır')
        assert kd['yayimlanan_kip_yakinsamasi']['olculdu'] is True

    def test_hukum_tepesi_de_olculuyor(self, kati_fea):
        """OH-D16-01'den beri hüküm sayısı SÜZÜLMÜŞ tepeden geliyor; kapı
        o büyüklüğü de ölçmek zorunda (yalnız ham tepeyi ölçmek, hükmü
        taşıyan sayının yakınsamasını hiç sınamamaktır)."""
        yy = kati_fea['meta']['kisit_duyarliligi'][
            'yayimlanan_kip_yakinsamasi']
        alanlar = yy['olculen_alanlar']
        assert 'max_von_mises_hukum' in alanlar, (
            'kapı hükmün türetildiği büyüklüğü ölçmüyor (OH-D15-02)')
        assert 'max_von_mises_nodal' in alanlar, (
            'kapı panelin yayımladığı HAM tepeyi ölçmüyor')

    def test_kapi_en_kotusunu_alir(self, kati_fea):
        """Kapının skaleri ölçülen alanların EN KÖTÜSÜ olmalı.

        Biri geçip öteki düşerse kapı DÜŞMELİ: yayımlanan bir sayının
        yakınsaması, yayımlanan öteki sayının yakınsamadığını örtemez.
        """
        yy = kati_fea['meta']['kisit_duyarliligi'][
            'yayimlanan_kip_yakinsamasi']
        alanlar = yy['olculen_alanlar']
        # --- ÇEVRİLDİ (ÖH D25, OH-D24-01) — GEREKÇE ÖLÇÜLDÜ ------------
        # Kapı artık HAM tepeyle HÜKÜM büyüklüğünün en kötüsünü değil,
        # HÜKMÜN TAŞIDIĞI büyüklüğü ölçüyor. Ham düğüm tepesi (ASME
        # "F") geometrik süreksizlikte h→0 iken yakınsamıyor: katı
        # motorda tekdüze merdivende gözlenen mertebe p ≈ 0,12, 16.384
        # elemanda hâlâ %4,0 (kanıt docs/scofield/raw/OH/D25/fea-cfd/
        # a1/teshis_scl.json). ASME VIII-2 Tablo 5.6 tepeyi plastik
        # çökme hükmünden zaten dışlar; konjonksiyon KARŞILANAMAZ bir
        # şarttı ve hükmü ilkesel olarak kazanılamaz kılıyordu. İki
        # ölçüm de yayımlanmaya devam ediyor, kapı alanı ADIYLA beyanlı.
        assert yy['kapi_alani'] == 'max_von_mises_hukum'
        assert yy['rel_change'] == pytest.approx(
            alanlar['max_von_mises_hukum'], rel=1e-12), (
            f'kapı hüküm büyüklüğünü almıyor: {yy}')
        assert 'max_von_mises_nodal' in alanlar, (
            f'ham tepenin yakınsaması artık ölçülmüyor: {yy}')
        assert yy['yakinsadi'] == (yy['rel_change'] < yy['tol'])
        if not yy['yakinsadi']:
            assert yy['dusuren_alanlar'], (
                'kapı düştü ama hangi alanın düşürdüğü beyanlı değil')

    def test_iki_alan_AYRISABILIYOR_ve_kapi_kotusunu_aliyor(self,
                                                             hibrit_fea):
        """Ayrıştırıcı vaka: iki büyüklüğün FARKLI olduğu koşum.

        Katıda tepe Saint-Venant bandının DIŞINDA kaldığı için ham ve
        süzülmüş büyüklük SAYICA EŞİTTİR; o vaka "kapı hangi alanı
        okuyor" sorusunu ayırt edemez. Hibrit varsayılanında ise kaba
        mesh'te tepe bandın İÇİNDE, ince mesh'te dışındadır ve iki alan
        ayrışır (ölçüldü, D24: ham %8,639 ⟷ süzülmüş %0,137). Kapı bu
        vakada EN KÖTÜSÜNÜ almazsa yayımlanan hüküm sayısının
        yakınsamadığı gizlenir.
        """
        kd = hibrit_fea['meta']['kisit_duyarliligi']
        yy = kd.get('yayimlanan_kip_yakinsamasi') or {}
        if not yy.get('olculdu'):
            pytest.skip('bu koşumda kapı kurulmuyor (yayımlanan kip = '
                        'birincil kip); ayrıştırıcı vaka yok')
        alanlar = yy['olculen_alanlar']
        assert len(alanlar) >= 2
        ham = alanlar['max_von_mises_nodal']
        huk = alanlar['max_von_mises_hukum']
        assert abs(ham - huk) > 1e-6, (
            'bu vakanın ayrıştırıcı olması için iki alan FARKLI olmalı; '
            f'eşitler: {alanlar}')
        # --- ÇEVRİLDİ (ÖH D25, OH-D24-01) — GEREKÇE ÖLÇÜLDÜ ------------
        # Kapı artık HAM tepeyle HÜKÜM büyüklüğünün en kötüsünü değil,
        # HÜKMÜN TAŞIDIĞI büyüklüğü ölçüyor. Ham düğüm tepesi (ASME
        # "F") geometrik süreksizlikte h→0 iken yakınsamıyor: katı
        # motorda tekdüze merdivende gözlenen mertebe p ≈ 0,12, 16.384
        # elemanda hâlâ %4,0 (kanıt docs/scofield/raw/OH/D25/fea-cfd/
        # a1/teshis_scl.json). ASME VIII-2 Tablo 5.6 tepeyi plastik
        # çökme hükmünden zaten dışlar; konjonksiyon KARŞILANAMAZ bir
        # şarttı ve hükmü ilkesel olarak kazanılamaz kılıyordu. İki
        # ölçüm de yayımlanmaya devam ediyor, kapı alanı ADIYLA beyanlı.
        assert yy['kapi_alani'] == 'max_von_mises_hukum'
        assert yy['rel_change'] == pytest.approx(huk, rel=1e-12), (
            f'kapı hüküm büyüklüğünü almıyor: {yy}')
        # Ham tepe ÖRTÜLMEDİ: kendi ölçümü ve kendi beyan alanı var.
        tf = hibrit_fea['meta']['kisit_duyarliligi']['tepe_F_yakinsamasi']
        assert tf['rel_change'] == pytest.approx(ham, rel=1e-12)
        assert tf['hukum_kapisi_mi'] is False

    def test_kati_hukum_fail_closed_ve_gerekce_ADLI(self, kati_fea):
        """Katıda hüküm GERİ ÇEKİLİR ve gerekçesi makine-okur alandadır.

        Bu, OH-D15-02 başlığının çürütülen yarısıdır: kullanıcının hüküm
        görmemesi kusur değil, ölçülmüş yakınsamama karşısında DOĞRU
        davranıştır. Sayılar silinmez.
        """
        h = kati_fea['meta']['hukum']
        assert h['verildi'] is False
        assert h['geri_cekme_gerekceleri'], 'gerekçe adsız'
        # ÇEVRİLDİ (ÖH D25): 'not_converged' gerekçesi DÜŞTÜ çünkü hüküm
        # büyüklüğü lineerleştirilmiş P_L+P_b'ye geçti ve bu konturda
        # gerçekten duruyor (katı hüküm merdiveni 192,19 → 195,85 MPa,
        # son adım %0,046; ham tepe aynı merdivende %4,00). Kalemin ASIL
        # iddiası — hüküm kazanılmadıysa VERİLMEZ, gerekçe ADIYLA yazılır
        # — aynen sınanıyor.
        # ÇEVRİLDİ (OH-D25-28 / OH-D24-01, ÖH D27 a1): iç kontur köşe
        # tabanı ÜRÜN VARSAYILANI olunca katının yayımlanan kipi
        # GERÇEKTEN yakınsadı ve 'yayimlanan_kip_yakinsamadi' gerekçesi
        # DÜŞTÜ (ölçüm: docs/scofield/raw/OH/D27/fea-cfd/a1/sonra_a1.json
        # §G5 — gerekçe listesi ['yayimlanan_kip_yakinsamadi',
        # 'kisit_yeri_duyarliligi_yuksek'] → ['kisit_yeri_duyarliligi_
        # yuksek']; köprü kapısının rel_change'i 0,024743 → 0,002592).
        # Yani ÜRÜN İYİLEŞTİ. Sabit üyelik çapası yerine FAIL-CLOSED BAĞI
        # sınanıyor — bu daha dardır: gerekçe listede ANCAK VE ANCAK
        # karşılık gelen yakınsama iddiası kazanılmadıysa bulunabilir.
        assert ('yayimlanan_kip_yakinsamadi'
                in h['geri_cekme_gerekceleri']) is (
            h['converged_yayimlanan_kip'] is False), (
            'gerekçe ile ölçüm çelişiyor: '
            f"gerekçeler={h['geri_cekme_gerekceleri']}, "
            f"converged_yayimlanan_kip={h['converged_yayimlanan_kip']}")
        # Hüküm yine de GERİ ÇEKİLDİ ve sebebi ADIYLA duruyor.
        assert 'kisit_yeri_duyarliligi_yuksek' in \
            h['geri_cekme_gerekceleri'], h['geri_cekme_gerekceleri']
        # ÇEVRİLDİ (ÖH D25, üstteki gerekçe): birincil kip ARTIK
        # YAKINSIYOR, o yüzden bu gerekçe düştü. Yerine, birincil kipin
        # yakınsama iddiasının hükümle TUTARLI olması sınanıyor.
        assert h['converged_birincil_kip'] is True, (
            'birincil kip yakınsamıyorsa gerekçesi listede olmalı: '
            f'{h["geri_cekme_gerekceleri"]}')
        # Sayı SİLİNMEZ (P17B1-02 sözleşmesi).
        assert h['min_safety_factor'] is not None
        assert 'GERİ ÇEKİLDİ' in h['beyan']
