"""ÖH Dalga-23 / termo-ucus aşama-1 bekçileri.

Kalemler: P4B3-23 (6-DOF ölü kod: Mach'a bağlı C_Nα/CP, jet sönümü, α
serisi tek kaynak), P4B3-24 (isp/bütçe çelişkisinin kütüphanede reddi),
P4B3-27 (LAUNCH_SITE_PRESETS ürün yolunda), P4B3-28 (parametrik taramada
paylaşılan analizör sızıntısı), P4B3-29 (ray boyu künyesi uçta),
P4B4-17 (çalkalanma çakışma bandının denetimi).

Her bekçi TERS-MUTASYONLA doğrulandı: onarım geçici olarak geri alındığında
ilgili test KIRMIZI oluyor (kanıt: docs/scofield/raw/OH/D23/termo-ucus/a1/
mutasyon.json).

ÖH D24 NOTU: P4B3-23 (a) D23'te ÇÜRÜTÜLMÜŞTÜ ("at_mach bağlanamaz").
Çürütmenin kök sebebi OH-D23-17 olarak açılmış ve D24'te ONARILMIŞTIR;
bu dosyadaki ``TestP4B323MachBagimliligiCurutuldu`` sınıfı bu yüzden
ÇEVRİLDİ (gerekçe sınıfın kendi docstring'inde). Yeni bekçiler:
tests/test_d24_termo_ucus_a1.py.
"""
import ast
import os

import numpy as np
import pytest

from hrma.analysis.six_dof_trajectory import (
    BarrowmanAero, SixDOFTrajectory, _alpha_deg_series, _atmosphere,
    _quat_to_dcm)

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _aero():
    return BarrowmanAero(body_diameter=0.15, nose_length=0.5,
                         body_length=3.0, nose_type='ogive', fin_count=4,
                         fin_root_chord=0.30, fin_tip_chord=0.15,
                         fin_span=0.15, fin_sweep=0.10)


def _cozucu(**kw):
    taban = dict(dry_mass=20.0, propellant_mass=8.0, thrust=5000.0,
                 burn_time=6.0, cd0=0.5, wind_speed=0.0,
                 launch_elevation_deg=90.0, coriolis=False,
                 launch_altitude=0.0, rail_length=5.0,
                 x_cg_full=1.7, x_cg_empty=1.6)
    taban.update(kw)
    return SixDOFTrajectory(aero=_aero(), **taban)


def _durum(V, h, w_b, elevation=90.0):
    """(t, y) durum vektörü: dik atış, hız +z, verilen gövde açısal hızı."""
    from hrma.analysis.six_dof_trajectory import _quat_from_elevation_azimuth
    q = _quat_from_elevation_azimuth(elevation, 0.0)
    return np.concatenate([[0.0, 0.0, h], [0.0, 0.0, V], q, w_b])


def _uygulanan_moment(cozucu, t, y):
    """``_derivatives``in fiilen uyguladığı gövde momentini w_dot'tan çıkarır."""
    m = cozucu._mass_at(t)
    x_cg = cozucu._cg_at(t)
    I = np.array(cozucu._inertia(m, x_cg))[[0, 1, 1]]
    w_b = y[10:13]
    w_dot = cozucu._derivatives(t, y)[10:13]
    return w_dot * I + np.cross(w_b, I * w_b), x_cg


# =====================================================================
# P4B3-23 (a) — ÇÜRÜTME GERİ ALINDI (ÖH D24 / OH-D23-17 onarıldı)
# =====================================================================
class TestP4B323MachBagimliligiCurutuldu:
    """ÇEVRİLDİ (ÖH D24 / OH-D23-17). Eski hâli KUSURU KORUYORDU.

    D23'te bu sınıf üç şeyi kilitliyordu:

      1. ``k(2,9) < 0,30``  — süpersonik çarpanın 2-B agresifliği,
      2. ``cn(2,5) < 0,45·cn₀`` ve ``x_cp − x_cp(2,5) > 0,6 m``,
      3. ``_derivatives`` içinde ``at_mach`` ÇAĞRILMAMASI.

    Üçü de bir ONARIMI değil, ÖLÇÜLMÜŞ BİR KUSURU tutuyordu: D23'te kök
    sebep (``_fin_compressibility_factor``ün 2-B süpersonik dalı) fizik
    kalemi sayılıp ertelenmişti, bekçi de "biri korelasyonu düzeltirse
    kırmızıya dönsün ve kalem yeniden açılsın" diye yazılmıştı. D24'te
    korelasyon DÜZELTİLDİ (kaynak + sembolik türetim + ölçüm:
    ``docs/scofield/raw/OH/D24/termo-ucus/a1/``), dolayısıyla bekçinin
    beklentileri TERSİNE çevrildi — istenen davranış artık budur.

    ÖLÇÜLEN (taban 88a29d3 → D24):
        k(2,9)              0,23387 → 0,77421
        statik marj M=2,5   +0,0395 → +4,2058 kalibre
        statik marj M=2,9   −0,6901 → +3,7390 kalibre
        B aracı (bağlıyken) takla   → apoje 14197,87 m

    Tam bekçi kümesi: ``tests/test_d24_termo_ucus_a1.py``.
    """

    def test_supersonik_dal_ARTIK_2B_orani_DEGIL(self):
        """EŞİKLERİ GEVŞETİLDİ (ÖH D25 / OH-D24-03) — gerekçe aşağıda.

        D24 eşikleri (k > 0,70; cn(2,5) > 0,90·cn₀; CP kaçışı < 0,06 m)
        süpersonik dalın UÇ MACH KONİSİ KAYBI OLMADAN hesaplandığı hâli
        kilitliyordu. D25'te o kayıp yazıldı (1 − 1/(4·β·AR_f)) ve düşük
        en-boyda narin-kanat kolu eklendi; kanat etkinliği M = 2,9'da
        %13,8 DÜŞTÜ — bu bir gerileme değil, ölçülmüş bir iyimserliğin
        giderilmesidir (docs/scofield/raw/OH/D25/termo-ucus/a1/).

        Eşikler, bekçinin ASIL amacını (2-B orana geri dönüşü yakalamak)
        koruyacak şekilde yeniden konuldu — 2-B değerler D23'te
        k(2,9) = 0,234 / CP kaçışı 0,6 m idi, yeni eşikler onlardan hâlâ
        çok uzaktır.

        ÖLÇÜLEN (D24 → D25):
            k(2,9)              0,77421 → 0,66756
            cn(2,5)/cn₀         0,88    → 0,80881
            CP kaçışı [m]       0,0574  → 0,10414
        """
        from hrma.analysis.six_dof_trajectory import (
            _fin_compressibility_factor)
        aero = _aero()
        k = _fin_compressibility_factor(2.9, aero._fin_aspect,
                                        aero._fin_cos_gamma)
        assert k > 0.55, (
            'süpersonik çarpan yeniden 2-B oranına düştüyse OH-D23-17 '
            f'yeniden açılmalı: k(2,9) = {k!r} (2-B değeri 0,234)')
        cn_m, x_cp_m = aero.at_mach(2.5)
        assert cn_m > 0.75 * aero.cn_alpha
        # CP kaçışı 0,6 m'den (D23'teki değerden) ÇOK daha küçük
        assert (aero.x_cp - x_cp_m) < 0.20

    def test_dinamik_ARTIK_at_mach_KULLANIYOR(self):
        """AST: ``_derivatives`` Mach'a bağlı (C_Nα, x_cp) çiftini çağırır."""
        kaynak = open(os.path.join(
            KOK, 'hrma/analysis/six_dof_trajectory.py'), encoding='utf-8')
        agac = ast.parse(kaynak.read())
        kaynak.close()
        govde = [d for d in ast.walk(agac)
                 if isinstance(d, ast.FunctionDef) and d.name == '_derivatives']
        assert len(govde) == 1
        cagrilar = {c.func.attr for c in ast.walk(govde[0])
                    if isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Attribute)}
        assert 'at_mach' in cagrilar, (
            'bağ söküldüyse P4B3-23 (a) yeniden açılmalı')

    def test_kunye_M0_degerlerini_yayimlamaya_devam_eder(self):
        c = _cozucu()
        r = c.solve(t_max=200.0)
        assert r['cn_alpha'] == pytest.approx(c.aero.cn_alpha, rel=0, abs=0)
        assert r['x_cp'] == pytest.approx(c.aero.x_cp, rel=0, abs=0)


# =====================================================================
# P4B3-23 (b) — jet sönümü
# =====================================================================
class TestP4B323JetSonumu:
    """``_mdot_at`` (F062) ürün yolunda hiç çağrılmıyordu (ölçüm: 0 çağrı).

    Jet sönümü M = −ṁ·(x_e − x_cg)²·ω dinamik basınca DEĞİL debiye bağlıdır;
    yanma boyunca vardır, yanma bitince kendiliğinden yok olur.
    """

    def test_yanma_sirasinda_ek_sonum_var_ve_dogru_buyuklukte(self):
        c = _cozucu()
        c._r0 = np.zeros(3)
        w = np.array([0.0, 1.0, 0.0])           # 1 rad/s pitch
        # Aerodinamik terimleri sıfırlamak için hızı eşiğin ALTINA al:
        # u_mag <= 0.5 m/s -> aero bloğu hiç çalışmaz, geriye yalnız jet
        # sönümü kalır. Böylece terim İZOLE ölçülür.
        y = _durum(0.2, 1000.0, w)
        t = 3.0                                  # t < t_burn
        M_b, x_cg = _uygulanan_moment(c, t, y)
        mdot = c._mdot_at(t)
        assert mdot > 0.0
        beklenen = -mdot * (c.aero.L - x_cg) ** 2 * w[1]
        assert float(M_b[1]) == pytest.approx(beklenen, rel=1e-9)
        assert float(M_b[1]) < 0.0, 'jet sönümü dönüşe KARŞI olmalı'

    def test_yanma_bitince_terim_yok_olur(self):
        c = _cozucu()
        c._r0 = np.zeros(3)
        y = _durum(0.2, 1000.0, np.array([0.0, 1.0, 0.0]))
        M_b, _ = _uygulanan_moment(c, 7.0, y)    # t > t_burn -> ṁ = 0
        assert c._mdot_at(7.0) == 0.0
        assert float(M_b[1]) == pytest.approx(0.0, abs=1e-12)

    def test_sonum_acisal_hizla_dogrusal_ve_isaret_tersine_doner(self):
        c = _cozucu()
        c._r0 = np.zeros(3)
        M1, _ = _uygulanan_moment(
            c, 3.0, _durum(0.2, 1000.0, np.array([0.0, 1.0, 0.0])))
        M2, _ = _uygulanan_moment(
            c, 3.0, _durum(0.2, 1000.0, np.array([0.0, 2.0, 0.0])))
        Mn, _ = _uygulanan_moment(
            c, 3.0, _durum(0.2, 1000.0, np.array([0.0, -1.0, 0.0])))
        assert float(M2[1]) == pytest.approx(2.0 * float(M1[1]), rel=1e-9)
        assert float(Mn[1]) == pytest.approx(-float(M1[1]), rel=1e-9)


# =====================================================================
# P4B3-23 (c) — α serisi TEK kaynak
# =====================================================================
class TestP4B323AlfaTekKaynak:
    def test_vektor_tanim_eski_skaler_tanimla_BIT_AYNI(self):
        """Silinen skaler döngünün TAM kopyası burada; iki tanım bit-aynı.

        Böylece "tek kaynağa indirdim" iddiası sayıyla kanıtlanır: eski
        kod ne üretiyorduysa vektörleştirilmiş tanım da AYNI baytları
        üretir (kaldırılan döngü bu testte referans olarak duruyor).
        """
        rng = np.random.default_rng(20260905)
        q = rng.normal(size=(4, 250))
        v = rng.normal(size=(3, 250)) * 400.0
        # bir kısım nokta eşiğin ALTINDA kalsın (α = 0 kolu da sınansın)
        v[:, ::7] *= 1e-4
        wind = np.array([3.0, -2.0, 0.5])

        beklenen = []
        for k in range(v.shape[1]):
            qk = q[:, k] / np.linalg.norm(q[:, k])
            C = _quat_to_dcm(qk)
            u_i = v[:, k] - wind
            if np.linalg.norm(u_i) > 0.5:
                u_b = C.T @ u_i
                beklenen.append(np.degrees(np.arctan2(
                    np.hypot(u_b[1], u_b[2]), abs(u_b[0]))))
            else:
                beklenen.append(0.0)

        yeni = _alpha_deg_series(q, v, wind)
        eski = np.array(beklenen)
        fark = np.max(np.abs(yeni - eski))
        # BİT-AYNI DEĞİL, ULP-AYNI: eski döngü Cᵀ·u'yu ``C.T @ u_i`` (BLAS
        # nokta çarpımı) ile, vektör tanım aynı toplamı AÇIK terimlerle
        # yazıyor. İki toplama SIRASI farklı olduğu için son bitler
        # ayrışabilir; ölçülen fark gürültü tabanının (1e-12) altındadır ve
        # α'nın kendisi derece mertebesindedir. Modelde değişiklik YOKTUR.
        assert fark < 1e-12, f'iki tanım ayrışmış: max fark {fark!r}'
        assert np.array_equal(yeni == 0.0, eski == 0.0), (
            '0,5 m/s hız eşiği kolu ayrışmış: hangi noktaların α = 0 '
            'sayıldığı iki tanımda aynı olmalı')

    def test_cozucu_serisi_uretilir_ve_makul(self):
        c = _cozucu(launch_elevation_deg=84.0, wind_speed=5.0,
                    wind_direction_deg=270.0)
        r = c.solve(t_max=200.0)
        assert r['alpha_deg'].size == r['time'].size > 10
        assert np.all(np.isfinite(r['alpha_deg']))

    def test_solve_govdesinde_ikinci_alfa_dongusu_YOK(self):
        """AST: ``solve`` içinde skaler α hesabı (arctan2) kalmadı."""
        kaynak = open(os.path.join(
            KOK, 'hrma/analysis/six_dof_trajectory.py'), encoding='utf-8')
        agac = ast.parse(kaynak.read())
        kaynak.close()
        govde = [d for d in ast.walk(agac)
                 if isinstance(d, ast.FunctionDef) and d.name == 'solve']
        assert len(govde) == 1
        adlar = [c.func.attr for c in ast.walk(govde[0])
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)]
        assert 'arctan2' not in adlar, (
            'solve() hâlâ kendi α tanımını taşıyor: _alpha_deg_series ile '
            'ayrışabilecek ikinci kopya')
        assert '_alpha_deg_series' in [
            c.func.id for c in ast.walk(govde[0])
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]


# =====================================================================
# P4B3-24 — isp/bütçe çelişkisi kütüphanede REDDEDİLİR
# =====================================================================
class TestP4B324IspCelisikiRed:
    @staticmethod
    def _coz(isp=None):
        from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
        ta = TrajectoryAnalyzer()
        ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15,
                                  drag_coefficient=0.5, length=3.0)
        md = {'thrust': 5000.0, 'burn_time': 10.0, 'total_impulse': 50000.0,
              'propellant_mass_total': 8.0}
        if isp is not None:
            md['isp'] = isp
        return ta.calculate_trajectory(
            md, {'launch_angle': 85.0, 'launch_altitude': 0.0}), md

    @pytest.mark.parametrize('isp', [220.0, 1.0, 1e9])
    def test_celisen_isp_istisna_atar(self, isp):
        from hrma.analysis.trajectory_analysis import TrajectoryInputError
        with pytest.raises(TrajectoryInputError) as hata:
            self._coz(isp=isp)
        kayit = hata.value.problems[0]
        assert kayit['field'] == 'motor_data.isp'
        assert kayit['reason'] == 'inconsistent_propellant_budget'
        assert 'no trajectory was computed' in kayit['detail']

    def test_isp_verilmezse_butceden_turetilir(self):
        _, md = self._coz(isp=None)
        assert md['isp'] == pytest.approx(50000.0 / (8.0 * 9.80665), rel=1e-9)
        assert 'because isp was not supplied' in md['isp_basis']

    def test_tutarli_isp_kabul_edilir(self):
        tutarli = 50000.0 / (8.0 * 9.80665)
        _, md = self._coz(isp=tutarli)
        assert md['isp'] == pytest.approx(tutarli)

    def test_http_ucu_422_verir(self):
        from hrma.app import app
        app.config['TESTING'] = True
        c = app.test_client()
        r = c.post('/api/trajectory-analysis', json={
            'thrust': 5000.0, 'burn_time': 10.0, 'total_impulse': 50000.0,
            'propellant_mass_total': 8.0, 'isp': 220.0,
            'vehicle_mass_dry': 20.0, 'vehicle_diameter': 0.15,
            'launch_angle': 85.0})
        assert r.status_code == 422


# =====================================================================
# P4B3-27 — hazır saha listesi ürün yolunda
# =====================================================================
class TestP4B327SahaKisayollari:
    """Kalem KISMEN kapandı: ASCII Türkçe temizlendi, liste HÂLÂ ölü.

    Listeyi bir uçtan yayımlamak denendi ve geri alındı: tüketicisi
    arayüzdür ve ``hrma/templates/launch_site.html`` bu dalgada kardeş dalda
    değiştirildiği için dokunulamıyor; tüketicisiz uç ise
    ``tests/test_d18_bekci_cevirisi_a1.py::TestP13B208UcPanelEnvanteri``
    bekçisinin adıyla yasakladığı şeydir. Bkz. rapor.md P4B3-27.
    """

    def test_kullaniciya_gorunen_adlarda_ASCII_turkce_yok(self):
        """Kural #24: 'bolge referansi' gibi ASCII'ye kaçmış Türkçe yasak."""
        from hrma.analysis.launch_site import LAUNCH_SITE_PRESETS
        for p in LAUNCH_SITE_PRESETS:
            assert 'bolge referansi' not in p['name'], p['name']
            assert 'referansi' not in p['name'], p['name']

    def test_yaklasik_kayitlar_bayrakla_ayrilmaya_devam_ediyor(self):
        """``approx`` verinin içinde duruyor (arayüze taşınması ayrı kalem)."""
        from hrma.analysis.launch_site import LAUNCH_SITE_PRESETS
        assert len(LAUNCH_SITE_PRESETS) == 14
        assert sum(1 for p in LAUNCH_SITE_PRESETS if p['approx']) == 2

    def test_liste_urun_yolunda(self):
        """ÇEVRİLDİ (ÖH D24 · P4B3-27). Eski hâli ``okuyucu == []`` bekliyordu.

        D23'te bu bir ÖLÇÜM TRİPWIRE'ıydı ve kendi docstring'i "biri
        listeyi bağlarsa bu test kırmızıya döner ve P4B3-27'nin kalan
        ayağı yeniden ölçülür" diyordu. D24'te kalan ayak kapatıldı:
        ``/launch-site`` rotası listeyi şablona veriyor
        (``hrma/app.py::launch_site_page``) ve ``launch_site.html``
        gömülü 7 kayıtlık kopyasını bıraktı. Beklenti bu yüzden TERSİNE
        çevrildi — liste ARTIK okunmalı; okunmuyorsa kopya geri gelmiş
        demektir.
        """
        import os as _os
        okuyucu = []
        for kok, _alt, dsy in _os.walk(_os.path.join(KOK, 'hrma')):
            for d in dsy:
                if not d.endswith(('.py', '.js', '.html')):
                    continue
                tam = _os.path.join(kok, d)
                if _os.path.relpath(tam, KOK) == 'hrma/analysis/launch_site.py':
                    continue
                try:
                    with open(tam, encoding='utf-8') as f:
                        if 'LAUNCH_SITE_PRESETS' in f.read():
                            okuyucu.append(_os.path.relpath(tam, KOK))
                except (OSError, UnicodeDecodeError):
                    pass
        assert 'hrma/app.py' in okuyucu, (
            'liste ürün yolunda DEĞİL — P4B3-27 kopyası geri gelmiş '
            f'olabilir: {okuyucu}')


# =====================================================================
# P4B3-28 — parametrik tarama paylaşılan nesneyi kirletmez
# =====================================================================
class TestP4B328TaramaDurumSizintisi:
    def test_tarama_modul_nesnesini_degistirmez(self):
        """ÖH D33 · OH-UC-07 (fix-36b, 16 Eyl 2026): paylaşılan modül düzeyi
        ``trajectory_analyzer`` KALDIRILDI (ölü nesneydi: ürün yolunda global
        okuma 0; tarama ve iki uç kendi nesnesini kurar). Eski ayak paylaşılan
        nesnenin tarama tarafından EZİLMEDİĞİNİ ölçüyordu; yeni ayak sızıntı
        kanalının VAR OLMADIĞINI kilitler (kanal ölçülmez, imkânsız olur) ve
        tarama yolunun aynı gövdeyle hâlâ 200 döndüğünü doğrular."""
        import hrma.app as app_mod
        app_mod.app.config['TESTING'] = True
        assert not hasattr(app_mod, 'trajectory_analyzer'), (
            'modul duzeyi paylasilan TrajectoryAnalyzer geri geldi (OH-UC-07)')
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(kok, 'hrma', 'app.py'), encoding='utf-8') as f:
            agac = ast.parse(f.read())
        modul_duzeyi = [
            n.lineno for n in agac.body if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == 'trajectory_analyzer'
                    for t in n.targets)]
        assert modul_duzeyi == [], (
            'app.py modul duzeyinde trajectory_analyzer atamasi: %r' % modul_duzeyi)
        r = app_mod.app.test_client().post('/parametric-analysis', json={
            'param_type': 'of_ratio', 'param_start': 5.0, 'param_end': 7.0,
            'param_steps': 3, 'thrust': 1000, 'burn_time': 10,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o', 'of_ratio': 6.0,
            'include_trajectory': True, 'vehicle_mass_dry': 50,
            'vehicle_diameter': 0.15})
        assert r.status_code == 200


# =====================================================================
# P4B3-29 — ray boyu künyesi uçta
# =====================================================================
class TestP4B329RayBoyuKunyesi:
    @staticmethod
    def _uc(**ek):
        from hrma.app import app
        app.config['TESTING'] = True
        yuk = {'dry_mass': 20.0, 'propellant_mass': 8.0, 'thrust': 5000.0,
               'burn_time': 6.0, 'body_diameter': 0.15, 'body_length': 3.0,
               'nose_length': 0.5, 'launch_elevation_deg': 84.0,
               'x_cg_full': 1.7, 'x_cg_empty': 1.6}
        yuk.update(ek)
        return app.test_client().post('/api/six-dof-analysis',
                                      json=yuk).get_json()

    def test_verilmediginde_varsayilan_ADIYLA_yayimlanir(self):
        from hrma.analysis.six_dof_trajectory import DEFAULT_RAIL_LENGTH_M
        ozet = self._uc()['summary']
        assert ozet['rail_length_m'] == pytest.approx(DEFAULT_RAIL_LENGTH_M)
        assert ozet['rail_length_source'] == 'default'

    def test_verildiginde_kaynak_supplied_olur(self):
        ozet = self._uc(rail_length=2.5)['summary']
        assert ozet['rail_length_m'] == pytest.approx(2.5)
        assert ozet['rail_length_source'] == 'supplied'


# =====================================================================
# P4B4-17 — çalkalanma çakışma bandı denetlenir
# =====================================================================
class TestP4B417CakismaBandi:
    TABAN = dict(radius=0.5, fill_height=1.2, g_eff=9.80665,
                 liquid_mass=900.0, control_frequencies=[0.6, 1.0],
                 structural_frequencies=[12.0])

    @pytest.mark.parametrize('marj', [-1.0, 0.0, float('nan'),
                                      float('inf'), 5.0, 'abc'])
    def test_gecersiz_marj_REDDEDILIR(self, marj):
        from hrma.analysis.slosh_analysis import analyze_slosh
        with pytest.raises(ValueError) as hata:
            analyze_slosh(coincidence_margin=marj, **self.TABAN)
        assert 'coincidence_margin' in str(hata.value)

    @pytest.mark.parametrize('marj', [0.05, 0.20, 1.0])
    def test_gecerli_marj_taramayi_kosar(self, marj):
        from hrma.analysis.slosh_analysis import analyze_slosh
        r = analyze_slosh(coincidence_margin=marj, **self.TABAN)
        assert isinstance(r['coincidence_warnings'], list)

    def test_negatif_marj_sessiz_temiz_sonuc_uretmez(self):
        """Kusurun kendisi: −1,0 marj HTTP 200 + BOŞ uyarı listesi veriyordu.

        ÖLÇÜLDÜ (taban ef527ae, once.json P4B4_17): margin = −1,0 -> durum
        200, uyarı sayısı 0; kullanıcı 'çakışma riski yok' diye okuyordu,
        oysa tarama hiç yapılmamıştı.
        """
        from hrma.app import app
        app.config['TESTING'] = True
        r = app.test_client().post('/api/slosh-analysis', json=dict(
            self.TABAN, coincidence_margin=-1.0))
        assert r.status_code == 400
        assert 'coincidence_margin' in r.get_json()['error']

    def test_esik_TEK_kaynak(self):
        from hrma.analysis import slosh_analysis as sa
        assert sa.COINCIDENCE_MARGIN_MAX == 1.0
        kod = open(os.path.join(KOK, 'hrma/app.py'), encoding='utf-8').read()
        assert 'COINCIDENCE_MARGIN_MAX' not in kod, (
            'uç kendi kopyasını yazmamalı; kütüphanenin ValueError\'ını '
            '400 olarak geçirir')
