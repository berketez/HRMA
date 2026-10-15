# tests — ÖH Dalga-17 · kulvar fea-cfd · aşama 1 bekçileri
"""Dalga-17 fea-cfd onarımlarının TERS-MUTASYONLA kanıtlanmış bekçileri.

Kapsanan kalemler (kanıt: docs/scofield/raw/OH/D17/fea-cfd/a1/):

  EK-1     [ŞART Fable-D15] ``bridge.extract_thermal_inputs`` içindeki
           ``_red`` yardımcısının konumsal parametresi eskiden ``missing``
           adındaydı ve İKİ çağrı (burn_time / ısıl malzeme dalları) aynı
           adı uyarı parametresi olarak da geçiriyordu → TypeError. Yani
           fail-closed yolun KENDİSİ kapalıydı. D15'te ad çakışması
           kaldırıldı; Fable denetçisi DOĞRUDAN bekçi şart koştu: iki dal
           da ``run_thermal_from_motor`` üstünden, NOT_MODELLED + doğru
           missing/warning ile sınanır (TypeError değil).

  P6B1-05  ``settle_window`` üstünde HİÇBİR kapı yoktu; 2'nin altında
           hüküm ölçütü kendini boş yere doğruluyordu (ölçüldü:
           once.json → w=1'de yayımlanan bant tam 0,0; w=0'da ``hist[-0:]``
           TÜM GEÇMİŞ; w<0'da ham IndexError sızıyordu).

  P6B1-07  Boğazın iki tanımı ayrışıyordu ve çözücü "en küçük kolon"u
           koşulsuz BOĞAZ diye yayımlıyordu. Salt ıraksak konturda kolon
           minimumu UÇ kolona düşüyor (ölçüldü: i=0, yarıçapta +%3,33 /
           alanda +%6,78 ni=20'de; kabalaştıkça büyür) ve ayrılma köprüsü
           bu indisi devralıp tüm alanı "ıraksak bölge" sayıyordu.

  D15-CFD-02  ``tests/cfd/test_wall_output.py::test_FEA_koprusu_profili_
           KABUL_EDER``ın "tabanda da kırmızı" kaydı ÇÜRÜTÜLDÜ: taban
           2426b4d'de test YEŞİL (D15 fix-3'ün P8B2-04 boğaz-imzası
           onarımı kırmızıyı kapatmış). Buradaki bekçi o onarımın
           DURDUĞUNU kilitler.
"""

import numpy as np
import pytest


# =====================================================================
# Ortak fikstürler
# =====================================================================
@pytest.fixture(scope='module')
def BR():
    from hrma.fea import bridge
    return bridge


@pytest.fixture(scope='module')
def termal_kontur():
    """Yakınsak-ıraksak kontur + BOĞAZDA tepe yapan Bartz zarfı h(z).

    Uydurma değil: h ∝ (r*/r)^1,8 Bartz'ın kendi yarıçap bağımlılığıdır,
    dolayısıyla tepe tanım gereği en küçük yarıçapta olur ve köprünün
    P8B2-04 boğaz-hizası nirengisini GEÇER. Amaç kapıları geçip
    ISIL girdi dallarına ulaşmaktır.
    """
    z = np.linspace(0.0, 0.20, 21)
    r = 0.05 - 0.03 * np.exp(-((z - 0.10) / 0.03) ** 2)
    i_bogaz = int(np.argmin(r))
    hg = 12000.0 * (r[i_bogaz] / r) ** 1.8
    profil = {'x_mm': [float(v) for v in z * 1000.0],
              'h_g': [float(v) for v in hg],
              'T_recovery': [2800.0] * z.size}
    kontur = [[float(a), float(b)] for a, b in zip(z, r)]
    return kontur, profil, float(hg[i_bogaz])


def _motor(kontur, hg_bogaz, malzeme='steel_4130', burn_time=10.0):
    m = {
        'nozzle_contour': {'points': kontur},
        'chamber_pressure': 40.0,
        'structural_analysis': {
            'chamber_analysis': {'wall_thickness_used_mm': 5.0},
            'design_parameters': {'material': malzeme},
        },
        'heat_transfer_analysis': {
            'heat_transfer_coefficients': {'gas_side': hg_bogaz},
        },
    }
    if burn_time is not None:
        m['burn_time'] = burn_time
    return m


# =====================================================================
# EK-1 [ŞART Fable-D15] — _red ad çakışması: İKİ RED DALI DA ÇALIŞIR
# =====================================================================
class TestEK1_RedDallariCokmez:
    """Fable-D15 ŞARTI: burn_time'sız ve ısıl-özelliksiz motorla
    ``run_thermal_from_motor`` NOT_MODELLED + doğru missing/warning
    döndürür (TypeError DEĞİL) — iki dal da sınanır.

    TERS MUTASYON (mutasyon.json M1): ``def _red(eksikler, ...)`` →
    ``def _red(missing, ...)`` yapılınca iki çağrının ``missing=`` uyarı
    parametresi konumsal adla çakışır ve Python "aynı argümana iki değer"
    TypeError'ı atar; aşağıdaki iki test de KIRMIZI olur.
    """

    def test_saglikli_motor_kapilari_geciyor(self, BR, termal_kontur):
        """ÇAPA: aynı kurulum tam malzemeyle 'ok' — yani aşağıdaki iki
        red, kapıların gelişigüzel reddi değil ALANIN eksikliğidir."""
        kontur, profil, hg = termal_kontur
        o = BR.extract_thermal_inputs(_motor(kontur, hg),
                                      axial_profile=profil)
        assert o['status'] == BR.BRIDGE_STATUS_OK, o.get('reason')

    def test_burn_time_YOK_dali_NOT_MODELLED_doner(self, BR, termal_kontur):
        kontur, profil, hg = termal_kontur
        motor = _motor(kontur, hg, burn_time=None)
        # TypeError'ın kendisi de bir başarısızlıktır: pytest zaten
        # yükseltir, ama gerekçeyi ADIYLA yakalamak için sarıyoruz.
        try:
            o = BR.run_thermal_from_motor(motor, axial_profile=profil,
                                          ambient_temperature_K=293.15,
                                          n_axial=6, n_radial=3)
        except TypeError as exc:                       # pragma: no cover
            pytest.fail(
                '_red konumsal parametresi uyarı parametresiyle çakıştı — '
                f'fail-closed yolun KENDİSİ çöküyor: {exc}')
        assert o['status'] == BR.BRIDGE_STATUS_NOT_MODELLED
        assert o['missing'] == ['burn_time']
        assert o['warning']['code'] == BR.WARN_INPUTS_MISSING
        # Uyarı gövdesi eksik alanı ADIYLA taşır (çağrının missing=
        # parametresi buraya gider — çakışmanın kalktığının kanıtı).
        assert 'burn_time' in repr(o['warning'])
        assert 'burn_time' in o['reason']

    def test_isil_ozellik_YOK_dali_NOT_MODELLED_doner(
            self, BR, termal_kontur, monkeypatch):
        """Depoda E/ν'si olup ρ,c_p,k'si eksik malzeme YOK (24 kaydın
        24'ü ölçüldü), o yüzden bu dal ancak DB kaydı doktorlanarak
        gezilebilir: yapısal katman geçsin (E, ν, akma var) ama ısıl
        katman eksik kalsın (specific_heat düşürüldü)."""
        import hrma.data.materials_db as mdb

        gercek = mdb.get_material

        def _isilsiz(key, *a, **kw):
            rec = dict(gercek(key, *a, **kw))
            rec.pop('specific_heat', None)
            return rec

        monkeypatch.setattr(mdb, 'get_material', _isilsiz)

        kontur, profil, hg = termal_kontur
        motor = _motor(kontur, hg)
        try:
            o = BR.run_thermal_from_motor(motor, axial_profile=profil,
                                          ambient_temperature_K=293.15,
                                          n_axial=6, n_radial=3)
        except TypeError as exc:                       # pragma: no cover
            pytest.fail(
                '_red konumsal parametresi uyarı parametresiyle çakıştı — '
                f'fail-closed yolun KENDİSİ çöküyor: {exc}')
        assert o['status'] == BR.BRIDGE_STATUS_NOT_MODELLED
        assert o['missing'] == ['malzeme ısıl özellikleri (ρ, c_p, k)']
        assert o['warning']['code'] == BR.WARN_INPUTS_MISSING
        assert 'ısıl özellik' in repr(o['warning'])
        assert 'specific_heat_J_kgK' in o['reason']

    def test_red_konumsal_parametresi_uyari_adiyla_CAKISMIYOR(self, BR):
        """Yapısal kilit: kusurun KÖKÜ ad çakışmasıydı. Konumsal ad
        'missing' olmadığı sürece ``missing=`` uyarı parametresi güvenle
        geçirilebilir; ad geri dönerse bu bekçi doğrudan kırmızı olur."""
        import inspect
        src = inspect.getsource(BR.extract_thermal_inputs)
        imza = next(ln for ln in src.splitlines() if 'def _red(' in ln)
        konumsal = imza.split('(', 1)[1].split(',')[0].strip()
        assert konumsal != 'missing', (
            "_red'in konumsal parametresi yine 'missing' — iki çağrı "
            'missing= uyarı parametresi geçiriyor, TypeError geri geldi.')
        assert src.count('missing="') >= 2, (
            'uyarı parametresi olarak missing= geçen çağrılar kayboldu — '
            'bu bekçinin ölçtüğü çakışma vakası artık kurulmuyor olabilir')


# =====================================================================
# P6B1-05 — hüküm penceresi kapısı
# =====================================================================
class TestP6B1_05_HukumPenceresiKapisi:
    """``settle_window`` hüküm ölçütünün TANIM ALANIDIR; 2'nin altında
    ölçüt kendini boş yere doğruluyordu.

    TERS MUTASYON (M2): ``MIN_SETTLE_WINDOW = 2`` → ``0`` yapılınca kapı
    hem 0'ı hem 1'i geçirir ve bant yeniden 0,0 / tüm-geçmiş olur.
    """

    @pytest.fixture(scope='class')
    def ST(self):
        from hrma.cfd import steady
        return steady

    @pytest.fixture(scope='class')
    def kucuk_grid(self):
        from hrma.cfd.grid_axisym import build_grid_from_wall
        z = np.linspace(0.0, 0.20, 25)
        r = (0.03 + 0.02 * (z / 0.20) ** 2
             + 0.01 * np.cos(np.pi * z / 0.20))
        return build_grid_from_wall(z, r, 6)

    def _kos(self, ST, grid, **kw):
        return ST.solve_steady_axisym(grid, P0=2.0e6, T0=2800.0, gamma=1.2,
                                      R=350.0, Pb=1.0e5, max_iters=3,
                                      tol_res=1e-30, **kw)

    @pytest.mark.parametrize('w', [0, 1, -3])
    def test_pencere_2den_KUCUK_ADLI_retle_reddedilir(self, ST, kucuk_grid, w):
        with pytest.raises(ValueError) as ex:
            self._kos(ST, kucuk_grid, settle_window=w, settle_tol=1e-11)
        m = str(ex.value)
        assert 'settle_window' in m and str(ST.MIN_SETTLE_WINDOW) in m
        # Ham IndexError SIZMAZ (w=-3 eskiden onu atıyordu).
        assert 'index out of range' not in m

    def test_kesirli_ve_bool_pencere_reddedilir(self, ST, kucuk_grid):
        for w in (2.5, True):
            with pytest.raises(ValueError, match='settle_window'):
                self._kos(ST, kucuk_grid, settle_window=w, settle_tol=1e-11)

    def test_saglikli_pencere_KESILMEZ(self, ST, kucuk_grid):
        """Kapı bir gevşetme değil ama sağlıklı koşuyu da kesmemeli."""
        s = self._kos(ST, kucuk_grid,
                      settle_window=ST.MIN_SETTLE_WINDOW, settle_tol=1e-11)
        assert s['settle_bands']['window'] == ST.MIN_SETTLE_WINDOW
        s2 = self._kos(ST, kucuk_grid, settle_window=200, settle_tol=1e-11)
        assert s2['settle_bands']['window'] == 200

    def test_varsayilan_pencere_DEGISMEDI(self, ST):
        """Bit-özdeşlik sözleşmesi: varsayılan 200'dür ve kapı onu
        etkilemez (dört Euler referansı bu varsayılan üstünde duruyor)."""
        assert ST.DEFAULT_SETTLE_WINDOW == 200
        assert ST.MIN_SETTLE_WINDOW == 2
        assert ST.DEFAULT_SETTLE_WINDOW >= ST.MIN_SETTLE_WINDOW

    def test_bant_aritmetigi_tanim_alani_disinda_NaN_doner(self, ST):
        """``_settle_band`` doğrudan da çağrılabiliyor; 2'nin altında
        sayı ÜRETMEZ. Eski davranış ölçüldü (once.json): w=0 → 0,8
        (TÜM GEÇMİŞİN bandı), w=1 → 0,0 ('kusursuz oturma')."""
        hist = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert np.isnan(ST._settle_band(hist, 0))
        assert np.isnan(ST._settle_band(hist, 1))
        assert np.isnan(ST._settle_band([3.0], 1))
        # 2 ve üstü: tanımlı ve SON pencereyi okur (tüm geçmişi değil)
        assert ST._settle_band(hist, 2) == pytest.approx((5.0 - 4.0) / 5.0)
        assert ST._settle_band(hist, 5) == pytest.approx((5.0 - 1.0) / 5.0)
        # pencere dolmadıysa hâlâ NaN ("bilinmiyor" ≠ "oturdu")
        assert np.isnan(ST._settle_band(hist, 200))

    def test_pencere_0_TUM_GECMISI_okumuyor(self, ST):
        """Kusurun ikinci yüzü: ``hist[-0:]`` 'pencere yok' değil TÜM
        GEÇMİŞ demektir. Kapı sonrası bu yol hiç kurulmuyor."""
        hist = [1.0, 2.0, 3.0, 4.0, 5.0]
        tum_gecmis_bandi = (max(hist) - min(hist)) / abs(hist[-1])
        assert ST._settle_band(hist, 0) != tum_gecmis_bandi
        assert np.isnan(ST._settle_band(hist, 0))


# =====================================================================
# P6B1-07 — boğaz imzası: uç kolon boğaz DEĞİLDİR
# =====================================================================
class TestP6B1_07_BogazImzasi:
    """Çözücü "en küçük kolon"u koşulsuz boğaz diye yayımlıyordu.

    TERS MUTASYON (M3): ``'interior': bool(0 < i_throat < ...)`` →
    ``True`` yapılınca uç kolon yine boğaz sayılır ve ayrılma köprüsü
    onu devralır.
    """

    @pytest.fixture(scope='class')
    def ST(self):
        from hrma.cfd import steady
        return steady

    @pytest.fixture(scope='class')
    def salt_iraksak(self, ST):
        """Yarıçapı girişten çıkışa TEKDÜZE artan kontur: boğaz alanın
        KENARINDADIR, yani gerçek bir boğaz yoktur."""
        from hrma.cfd.grid_axisym import build_grid_from_wall
        ni = 20
        z = np.linspace(0.0, 0.20, ni + 1)
        r = 0.030 + (0.070 - 0.030) * (z / 0.20)
        grid = build_grid_from_wall(z, r, 6)
        s = ST.solve_steady_axisym(grid, P0=2.0e6, T0=2800.0, gamma=1.2,
                                   R=350.0, Pb=None, max_iters=3,
                                   tol_res=1e-30)
        return z, r, s

    @pytest.fixture(scope='class')
    def yakinsak_iraksak(self, ST):
        """Gerçek C-D kontur: boğaz İÇ kolonda."""
        from hrma.cfd.grid_axisym import build_grid_from_wall
        z = np.linspace(0.0, 0.20, 21)
        r = 0.030 + 0.030 * ((z - 0.08) / 0.08) ** 2
        grid = build_grid_from_wall(z, r, 6)
        s = ST.solve_steady_axisym(grid, P0=2.0e6, T0=2800.0, gamma=1.2,
                                   R=350.0, Pb=None, max_iters=3,
                                   tol_res=1e-30)
        return s

    def test_UC_kolon_bogaz_IDDIASI_tasimaz(self, salt_iraksak):
        z, r, s = salt_iraksak
        t = s['throat']
        assert t['i'] == 0, 'fikstür beklenmedik — boğaz uçta olmalı'
        assert t['interior'] is False
        assert 'UÇ kolonda' in t['interior_basis']

    def test_iki_tanimin_farki_YAYIMLANIYOR_ve_gizlenmiyor(self, salt_iraksak):
        """Sayı SİLİNMEZ: kolon yarıçapı olduğu gibi durur, ama iki
        tanımın farkı ölçülebilir ve beyan bunu söyler."""
        z, r, s = salt_iraksak
        t = s['throat']
        dugum_min = float(np.min(r))
        assert t['radius_m'] > dugum_min, (
            'kolon yarıçapı düğüm minimumuna YENİDEN YAZILMIŞ — iki tanım '
            'birbirine eşitlenmemeliydi')
        bagil = (t['radius_m'] - dugum_min) / dugum_min
        assert bagil > 0.01, bagil
        assert 'yarım hücre' in t['interior_basis']

    def test_IC_kolon_bogaz_IDDIASI_tasir(self, yakinsak_iraksak):
        t = yakinsak_iraksak['throat']
        assert 0 < t['i'] < len(yakinsak_iraksak['section_average']['z_m']) - 1
        assert t['interior'] is True
        assert 'İÇ kolonda' in t['interior_basis']

    def test_ayrilma_koprusu_bogaz_IDDIASI_YOKSA_REDDEDER(self, salt_iraksak):
        from hrma.cfd import separation
        z, r, s = salt_iraksak
        z_wall = np.asarray(s['wall_pressure_z_m'], dtype=float)
        with pytest.raises(ValueError) as ex:
            separation._resolve_throat_index(s, z_wall)
        m = str(ex.value)
        assert "throat['interior']" in m
        assert 'İDDİA ETMİYOR' in m

    def test_ayrilma_koprusu_saglikli_bogazi_KESMEZ(self, yakinsak_iraksak):
        from hrma.cfd import separation
        s = yakinsak_iraksak
        z_wall = np.asarray(s['wall_pressure_z_m'], dtype=float)
        i_t, beyan = separation._resolve_throat_index(s, z_wall)
        assert i_t == s['throat']['i']
        assert 'İDDİA EDİYOR' in beyan

    def test_imzasiz_ESKI_sonuc_kesilmez_ama_BEYAN_EDILIR(self,
                                                          yakinsak_iraksak):
        """Geriye uyum: ``interior`` alanı olmayan (eski sürüm) sonuçta
        kapı ÇALIŞTIRILAMAZ ve bu beyan edilir — sessizce 'geçti'
        sayılmaz."""
        from hrma.cfd import separation
        s = dict(yakinsak_iraksak)
        s['throat'] = {k: v for k, v in s['throat'].items()
                       if k != 'interior'}
        z_wall = np.asarray(s['wall_pressure_z_m'], dtype=float)
        i_t, beyan = separation._resolve_throat_index(s, z_wall)
        assert i_t == s['throat']['i']
        assert 'YAYIMLAMIYOR' in beyan and 'sınanamadı' in beyan


# =====================================================================
# D15-CFD-02 — "tabanda kırmızı" kaydı ÇÜRÜTÜLDÜ
# =====================================================================
class TestD15CFD02_TabandaKirmiziCurutuldu:
    """Defter kalemi ``tests/cfd/test_wall_output.py::
    test_FEA_koprusu_profili_KABUL_EDER`` için "tabanda kırmızı" diyordu
    (D16 kaydı, taban 6fde52b). Taban 2426b4d'de ÖLÇÜLDÜ: test YEŞİL
    (1 passed, 131,39 s). Kırmızıyı kapatan D15 fix-3 onarımı köprünün
    P8B2-04 kapısına "boğaz imzası" ayrımını getirmişti; bu bekçi o
    ayrımın DURDUĞUNU kilitler (pahalı CFD fikstürünü kurmadan).
    """

    def test_bogaz_imzasi_UC_istasyonda_kapi_CALISTIRILAMAZ_der(
            self, BR, termal_kontur):
        """CFD ile çözülmüş profilde h(z) tepesi GİRİŞTEDİR (sınır
        tabakası orada sıfır kalınlıktan başlar). Eski kapı bunu "iç
        istasyonlar kaymış" diye reddediyordu; onarım 'boğaz imzası
        yok' deyip nirengiyi ÇALIŞTIRMIYOR."""
        kontur, profil, hg = termal_kontur
        # h(z) tepesi UÇ istasyona (giriş) alınır — CFD profilinin deseni:
        # sınır tabakası girişte sıfır kalınlıktan başlar, h orada en
        # büyüktür ve boğaza doğru TEKDÜZE azalır (bridge.py'nin ölçtüğü
        # desen: giriş 320.560 W/m²K → boğaz 51.845 W/m²K).
        n = len(profil['x_mm'])
        inen_h = [float(hg * (1.0 - 0.8 * i / (n - 1))) for i in range(n)]
        inen = {'x_mm': list(profil['x_mm']),
                'h_g': inen_h,
                'T_recovery': list(profil['T_recovery'])}
        # h_g MAKULLÜK kapısı (P8B2-01) profilin BOĞAZ İSTASYONUNDAKİ
        # değerini motorun kendi yayımladığı boğaz katsayısıyla
        # karşılaştırır; bu bekçinin konusu o kapı DEĞİL boğaz imzasıdır,
        # o yüzden çapa motorun alanına inen profilin KENDİ boğaz
        # istasyonundan verilir (uydurma değil: aynı profilin ölçümü).
        import numpy as _np
        i_bogaz = int(_np.argmin([pt[1] for pt in kontur]))
        o = BR.extract_thermal_inputs(_motor(kontur, inen_h[i_bogaz]),
                                      axial_profile=inen)
        assert o['status'] == BR.BRIDGE_STATUS_OK, (
            'CFD deseni profil yine reddediliyor — D15 fix-3 onarımı '
            f"düşmüş olabilir: {o.get('reason')}")
        hiza = o['_basis']['h_profili']['bogaz_hizasi']
        assert hiza['durum'] == 'calistirilamadi'
        assert 'boğaz imzası' in hiza['beyan']

    def test_IC_istasyonda_kaymis_profil_HALA_REDDEDILIR(self, BR,
                                                         termal_kontur):
        """Kapı GEVŞETİLMEDİ: tepe İÇ istasyondaysa hiza yeniden
        sınanır ve kaymış profil reddedilir."""
        kontur, profil, hg = termal_kontur
        n = len(profil['x_mm'])
        kaymis = dict(profil)
        # tepeyi 2. istasyona taşı (iç, ama boğazdan uzak)
        kaymis_h = [float(hg * (0.3 + 0.7 * np.exp(
            -((i - 2) / 1.5) ** 2))) for i in range(n)]
        kaymis['h_g'] = kaymis_h
        i_bogaz = int(np.argmin([pt[1] for pt in kontur]))
        o = BR.extract_thermal_inputs(_motor(kontur, kaymis_h[i_bogaz]),
                                      axial_profile=kaymis)
        assert o['status'] == BR.BRIDGE_STATUS_NOT_MODELLED
        assert 'boğaz hizası' in o['reason'] or 'hizalı değil' in o['reason']


# =====================================================================
# P8B4-11 [ŞART Fable-D15] + OH-D16-12 — irtifa ızgarası TAVAN satırı
# =====================================================================
class TestP8B411_IzgaraTavaniVakumDegildir:
    """Kart aynı metinde iki çelişen etiketle AYNI sayıyı basıyordu.

    Üretici (hibrit P1B3-01) onarıldıktan sonra ``vacuum_thrust``
    GERÇEK vakum limitidir ve ızgaranın ucu ``top_of_grid_thrust``
    alanındadır; kart okumasını güncellemedi.

    ÖLÇÜLDÜ (once_P8B4-11.json, hibrit HTPB/N2O F_sl=3000 N, eps=4):
        vacuum_thrust      = 3427,4312 N
        top_of_grid_thrust = 3404,3358 N   (20 km)
        fark               =   23,0954 N
      taban:  "Vacuum Thrust: 3427 N"
              "Altitude-grid ceiling (20000 m) thrust: 3427 N
               (NOT the vacuum value ...)"      ← AYNI SAYI, ÇELİŞEN ETİKET
      onarım: tavan satırı 3404 N basıyor, kaynağını adıyla söylüyor.

    TERS MUTASYON (M6): tavan okuması ``top_of_grid_thrust`` →
    ``vacuum_thrust``a döndürülünce bu sınıf KIRMIZI olur.
    """

    @pytest.fixture(scope='class')
    def client(self):
        from hrma.app import app
        app.config['TESTING'] = True
        return app.test_client()

    @pytest.fixture(scope='class')
    def hibrit_motor(self, client):
        r = client.post('/calculate', json={
            'motor_type': 'hybrid', 'thrust': 3000.0, 'burn_time': 40.0,
            'chamber_pressure': 20.0, 'of_ratio': 6.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o', 'initial_port_diameter': 0.05,
            'chamber_diameter_input': 120.0, 'l_star': 1.0,
            'expansion_ratio': 4.0, 'total_impulse': 120000.0,
            'include_plots': False, 'generate_cad': False,
            'calculate_trajectory': False,
            'include_combustion_analysis': False,
            'include_realtime_dashboard': False,
            'include_3d_visualization': False})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        return r.get_json()['motor']

    @pytest.fixture(scope='class')
    def metin(self, hibrit_motor):
        from hrma.visualization.advanced_results import (
            create_cea_style_results)
        return create_cea_style_results(hibrit_motor)

    @pytest.fixture(scope='class')
    def tavan_satiri(self, metin):
        satir = [ln for ln in metin.splitlines()
                 if ln.startswith('Altitude-grid ceiling')]
        assert satir, metin[-1500:]
        return satir[0]

    def test_uretici_iki_alani_da_yayimliyor_ve_AYRISIYOR(self,
                                                          hibrit_motor):
        """Çapa: bekçinin ölçtüğü ayrım gerçekten var mı? İki alan
        eşitse aşağıdaki kilitler anlamsızlaşırdı."""
        ta = hibrit_motor['thrust_altitude_analysis']
        assert ta.get('top_of_grid_thrust') is not None
        assert ta.get('top_of_grid_altitude_m') is not None
        assert ta.get('vacuum_thrust') is not None
        fark = abs(float(ta['vacuum_thrust'])
                   - float(ta['top_of_grid_thrust']))
        assert fark > 1.0, (
            f'iki alan ayrışmıyor (fark {fark:.4f} N) — bu vakada tavan ⟷ '
            'vakum kilidi ölçülemez')

    def test_tavan_satiri_URETICININ_IZGARA_alanlarindan_okur(
            self, hibrit_motor, tavan_satiri):
        ta = hibrit_motor['thrust_altitude_analysis']
        assert f"{float(ta['top_of_grid_thrust']):.0f} N" in tavan_satiri
        assert f"{float(ta['top_of_grid_altitude_m']):.0f} m" in tavan_satiri
        assert 'top_of_grid_thrust' in tavan_satiri, (
            'satır kaynağını ADIYLA söylemeli (hangi alandan okuduğu)')

    def test_tavan_satiri_VAKUM_sayisini_BASMIYOR(self, hibrit_motor,
                                                  tavan_satiri):
        """Kusurun kalbi: satır "NOT the vacuum value" derken vakum
        sayısını basıyordu."""
        ta = hibrit_motor['thrust_altitude_analysis']
        assert 'NOT the vacuum value' in tavan_satiri
        assert f"{float(ta['vacuum_thrust']):.0f} N" not in tavan_satiri

    def test_kart_ve_tavan_FARKLI_sayilar(self, metin, tavan_satiri):
        """Metinde iki sayı yan yana ve ayrı: vakum kartta, ızgara ucu
        tavan satırında."""
        import re
        kart = re.search(r'Vacuum Thrust: ([\d.]+) N', metin)
        tavan = re.search(r'thrust: ([\d.]+) N', tavan_satiri)
        assert kart and tavan
        assert float(kart.group(1)) != float(tavan.group(1)), (
            'kart ve tavan yine AYNI sayıyı basıyor — çelişki geri geldi')

    def test_izgara_ucu_metinde_GERCEKTEN_var(self, hibrit_motor,
                                              tavan_satiri):
        """Taban kusurunun ikinci yüzü: dürüst ızgara ucu (3404 N)
        metinde HİÇ YOKTU."""
        ta = hibrit_motor['thrust_altitude_analysis']
        izgara_sonu = ta['thrust_altitude_data'][-1]['thrust']
        assert float(ta['top_of_grid_thrust']) == pytest.approx(
            float(izgara_sonu), rel=0, abs=0)
        assert f"{float(izgara_sonu):.0f} N" in tavan_satiri
