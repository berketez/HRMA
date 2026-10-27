"""ÖH Z5S / PK2 — uçuş köprüsü ve 6-DOF onarımlarının DAVRANIŞ bekçileri.

Paket: PK2-ucus-koprusu (defter kalemleri P4B3-01, -04, -07, -08, -09, -11,
-19, -20). Bu dosya onarılan sözleşmeleri kilitler; kapanış ölçütünü
(mevcut xfail borç imlerinin sökülmesi) tamamlayan İKİNCİ katmandır.

Bekçi felsefesi (kampanya kuralı): DAVRANIŞ ve KÜNYE kilitlenir, kesin
ondalık ÇAPALANMAZ. Eşzamanlı onarım dalgaları değerleri kaydırabilir;
ölçülen kesin değerler kanıt dosyalarındadır
(``docs/scofield/raw/OH/Z5S/pk2/capa_ONCE.json`` ⟷ ``capa_SONRA.json``).

KRİTİK KİLİT — ÖH D21 bekci-cevirisi a1 (defter OH-Z5-10). BU DOSYA
SİLİNEMEZ / ZAYIFLATILAMAZ. Gerekçe ölçüldü: Z5S'te sökülen xfail
borç imlerinden ikisi (``tests/test_six_dof_trajectory.py::
test_cg_verilmediginde_beyan_edilir`` ve ``tests/test_flight_vehicle.py::
test_inert_tank_kutlesini_icerir_ya_da_beyan_eder``) yalnız VARLIK
denetimi yapar — künyenin/beyanın var olduğunu sorar, DOĞRU olduğunu
sormaz. Künye DOĞRULUĞUNU tek başına bu dosya kilitler; bu dosya
düşerse o iki alanın içeriği hiçbir bekçi tarafından sınanmaz.
Makine okunur imi: ``KRITIK_KILIT`` modül sabiti (bkz. aşağı). Özel
``pytest`` imi BİLEREK kullanılmadı: depoda kayıtlı özel im yok
(ölçüldü — yalnız parametrize/skipif/xfail), yeni bir im her toplamada
``PytestUnknownMarkWarning`` üretirdi.

Kapsam dışı (bilinçli):
  * ``hrma/app.py`` — /api/six-dof-analysis sabit bir ``summary`` anahtar
    listesi seçtiği için CG künyesi ve ikame künyesi tüketiciye ULAŞMIYOR;
    uç katmanı bu paketin sahası değildir (paket notu).
  * P15B2-02 (ikiz ``_mm_to_m``, işaret kapısı) — dışlanan kalem; bu dosya
    o soruyu SORMAZ ve mevcut xfail borç imleri yerinde bırakılmıştır.
"""

import pathlib
import re

import numpy as np
import pytest

from hrma.analysis import flight_vehicle as fv

#: ÖH D21 / OH-Z5-10 — bekçi kaydı imi (makine okunur).
#: Bu dosya, aşağıdaki testlerin YALNIZ VARLIK sorduğu künyelerin
#: DOĞRULUĞUNU kilitleyen tek katmandır.
KRITIK_KILIT = {
    'kalem': 'OH-Z5-10',
    'gerekce': ('sökülen xfail testlerinden ikisi yalnız varlık '
                'denetimi yapıyor; künye doğruluğunu tek başına bu '
                'dosya kilitliyor'),
    'yalniz_varlik_soran_kardesler': (
        'tests/test_six_dof_trajectory.py::'
        'test_cg_verilmediginde_beyan_edilir',
        'tests/test_flight_vehicle.py::'
        'test_inert_tank_kutlesini_icerir_ya_da_beyan_eder'),
}

from hrma.analysis.six_dof_trajectory import (
    CG_ASSUMED_EMPTY_FRACTION, CG_ASSUMED_FULL_FRACTION, G0, R_EARTH,
    BarrowmanAero, SixDOFTrajectory, _quat_from_elevation_azimuth,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
LAUNCH_SITE_HTML = REPO / 'hrma' / 'templates' / 'launch_site.html'


# ---------------------------------------------------------------------------
# Ortak fikstürler
# ---------------------------------------------------------------------------

def _arac():
    """Kanatlı temsili araç (kanatsız araç tumble_event ile anında biter)."""
    return BarrowmanAero(
        body_diameter=0.10, nose_length=0.40, body_length=2.0,
        nose_type='ogive', fin_count=4, fin_root_chord=0.20,
        fin_tip_chord=0.10, fin_span=0.11, fin_sweep=0.08)


def _cozucu(**kw):
    kwargs = dict(dry_mass=8.0, propellant_mass=4.0, thrust=1200.0,
                  burn_time=6.0, cd0=0.45, wind_speed=0.0,
                  launch_elevation_deg=89.0)
    kwargs.update(kw)
    return SixDOFTrajectory(aero=_arac(), **kwargs)


def _serbest_dusus_ivmesi(solver, h_agl):
    """``_derivatives``in UYGULADIĞI düşey ivme [m/s²] (yalnız yerçekimi).

    Yanma bitmiş (itki 0), hız sıfır (aerodinamik terim kapalı, u_mag < 0.5)
    ve ray aşılmış bir durum vektöründe geriye yalnız −g kalır. Böylece g
    ifadesi çözücünün İÇİNDEN, aracı yeniden uçurmadan okunur.
    """
    solver._r0 = np.zeros(3)
    q = _quat_from_elevation_azimuth(90.0, 0.0)
    y = np.concatenate([[0.0, 0.0, float(h_agl)], [0.0, 0.0, 0.0], q,
                        [0.0, 0.0, 0.0]])
    t = solver.t_burn + 1.0
    return float(solver._derivatives(t, y)[5])


def _eksenel_ivme(solver, h_agl, v_up):
    """Aerodinamik terim AÇIKKEN düşey ivme — yoğunluğa duyarlı probe."""
    solver._r0 = np.zeros(3)
    q = _quat_from_elevation_azimuth(90.0, 0.0)
    y = np.concatenate([[0.0, 0.0, float(h_agl)], [0.0, 0.0, float(v_up)], q,
                        [0.0, 0.0, 0.0]])
    t = solver.t_burn + 1.0
    return float(solver._derivatives(t, y)[5])


# ===========================================================================
# P4B3-01 — fırlatma sahası rakımı atmosfere GİRER
# ===========================================================================

class TestSahaRakimiAtmosfere:
    """Atmosfer MUTLAK irtifanın fonksiyonudur (USSA 1976 profil tanımı).

    ÖNCE (ölçüldü, HEAD 9ddbb22): 0 m ⟷ 3000 m saha arasında apoje farkı
    0,000e+00 — durum vektörünün AGL yüksekliği doğrudan tabloya
    veriliyordu, yani her saha deniz seviyesinde varsayılıyordu.
    """

    def test_ayni_agl_yuksekliginde_surukleme_rakimla_azalir(self):
        """Aynı AGL yüksekliği + aynı hız: yüksek sahada hava İNCE olmalı.

        Sürükleme aşağı yönlü (tırmanışta) olduğundan, ince havada düşey
        ivme daha AZ negatiftir. Bu probe çözücüyü uçurmaz; ``_derivatives``
        içindeki yoğunluğu doğrudan ölçer.
        """
        deniz = _eksenel_ivme(_cozucu(launch_altitude=0.0), 1000.0, 250.0)
        yayla = _eksenel_ivme(_cozucu(launch_altitude=3000.0), 1000.0, 250.0)
        assert yayla > deniz, (
            f'aynı AGL/hızda düşey ivme deniz seviyesi {deniz:.6f} ⟷ '
            f'3000 m sahada {yayla:.6f} m/s² — saha rakımı yoğunluğa girmiyor')
        # Fark ölçülebilir olmalı: koşum gürültüsü bekçiyi yeşile çeviremesin.
        assert abs(yayla - deniz) > 1e-3

    def test_rakim_artarken_apoje_monoton_yukselir(self):
        """0 → 1500 → 3000 m: ince hava, az sürükleme, YÜKSEK apoje."""
        apojeler = [_cozucu(launch_altitude=h).solve(t_max=300.0)['apogee']
                    for h in (0.0, 1500.0, 3000.0)]
        assert apojeler[0] < apojeler[1] < apojeler[2], (
            'saha rakımı arttıkça apoje artmalı; ölçülen: '
            + ', '.join(f'{a:.3f}' for a in apojeler))
        # F023 beyanının kendi eşiği: fark METRE mertebesinde GÖRÜNÜR olmalı.
        assert apojeler[2] - apojeler[0] > 1.0

    def test_mach_dizisi_de_ayni_atmosferi_kullanir(self):
        """Ses hızı da MUTLAK irtifadan okunur — tek koşumda iki atmosfer olmaz.

        Kusur yalnız ``_derivatives``te onarılsaydı ``solve()`` içindeki Mach
        geçmişi hâlâ AGL atmosferini kullanır, aynı uçuş iki farklı ses
        hızıyla raporlanırdı.
        """
        deniz = _cozucu(launch_altitude=0.0).solve(t_max=300.0)
        yayla = _cozucu(launch_altitude=3000.0).solve(t_max=300.0)
        assert float(np.max(yayla['mach'])) != pytest.approx(
            float(np.max(deniz['mach'])), rel=1e-9), (
            'tepe Mach saha rakımından etkilenmiyor — Mach geçmişi hâlâ '
            'sahaya göre yükseklikle çözülüyor')

    def test_deniz_seviyesi_kolu_eski_ifadeyle_bit_ayni(self):
        """``launch_altitude = 0`` + enlem yok: g ifadesi ESKİSİYLE BİT-AYNI.

        Onarımın sağlıklı yolu bozmadığının sözleşme kanıtı (kesin ondalık
        çapalamadan): eski kod ``g = G0·(R/(R+h))²`` idi.
        """
        s = _cozucu()
        for h in (0.0, 1000.0, 25000.0):
            beklenen = -G0 * (R_EARTH / (R_EARTH + h)) ** 2
            assert _serbest_dusus_ivmesi(s, h) == beklenen, (
                f'h={h} m: varsayılan kolda g ifadesi değişmiş')


# ===========================================================================
# P4B3-11 — WGS84 yerel yerçekimi dinamiğe GİRER
# ===========================================================================

class TestYerelYercekimi:
    """``self.g_surface`` hesaplanıp okunmuyordu (ölçüldü: apoje bit-eş)."""

    @pytest.mark.parametrize('enlem', [0.0, 39.0, 90.0])
    def test_dinamik_g_surface_i_okur(self, enlem):
        """Yerdeki düşey ivme TAM OLARAK ``−g_surface`` olmalı.

        Serbest-hava düzeltmesi sahanın kendi yarıçapından ölçülür; h=0'da
        çarpan 1'dir, yani ivme doğrudan yerel g'dir. Sabit bir sayı
        çapalanmaz — çözücünün kendi beyan ettiği alan okunur.
        """
        s = _cozucu(latitude_deg=enlem, coriolis=False)
        assert _serbest_dusus_ivmesi(s, 0.0) == -s.g_surface

    def test_enlem_apojeyi_kaydirir(self):
        """Kutupta ağırlık büyük → apoje düşük (ekvatorda tersi)."""
        ekvator = _cozucu(latitude_deg=0.0, coriolis=False)
        kutup = _cozucu(latitude_deg=90.0, coriolis=False)
        assert kutup.g_surface > ekvator.g_surface        # ön koşul
        a_ekv = ekvator.solve(t_max=300.0)['apogee']
        a_kut = kutup.solve(t_max=300.0)['apogee']
        assert a_ekv > a_kut, (
            f'ekvator {a_ekv:.3f} m ⟷ kutup {a_kut:.3f} m — %'
            f'{100 * (kutup.g_surface / ekvator.g_surface - 1):.3f} g farkı '
            'apojeye yansımıyor')
        assert a_ekv - a_kut > 1.0

    def test_saha_rakimi_iki_kez_sayilmaz(self):
        """Rakım hem ``g_surface``a hem düzeltmeye giriyorsa ÇİFT sayılırdı.

        ``g_surface`` zaten saha rakımındaki serbest-hava değeridir; ters
        kare düzeltmesi bu yüzden ``R + launch_altitude``tan başlar. Sözleşme:
        yerdeki (h_agl = 0) ivme, rakım ne olursa olsun, TAM ``−g_surface``.
        """
        for h_saha in (0.0, 1500.0, 3000.0):
            s = _cozucu(latitude_deg=39.0, coriolis=False,
                        launch_altitude=h_saha)
            assert _serbest_dusus_ivmesi(s, 0.0) == -s.g_surface, (
                f'saha {h_saha} m: rakım düzeltmesi iki kez uygulanmış')


# ===========================================================================
# P4B3-07 — uydurulan CG künyesiyle birlikte yayımlanır
# ===========================================================================

class TestCGKunyesi:
    """Kararlılık hükmü CG'den çıkar; hangi CG kullanıldığı söylenmeli.

    KANAL: künye UYARI değil ALAN kanalından yayımlanır. Gerekçe ürün
    dosyasında yazılı — uç ``warnings``i hiç döndürmüyor ve her backend
    ``warn.*`` kodu iki dilde sözlük karşılığı istiyor
    (``tests/test_i18n_common.py``), sözlük ise bu paketin sahası dışında.
    """

    def test_cg_verilmezse_kunye_yayimlanir(self):
        s = _cozucu()
        res = s.solve(t_max=300.0)
        assert res['x_cg_source'] == 'assumed_length_fraction'
        assert res['x_cg_is_estimate'] is True
        assert res['x_cg_full'] == pytest.approx(s.x_cg_full, rel=1e-12)
        assert res['x_cg_empty'] == pytest.approx(s.x_cg_empty, rel=1e-12)
        # Kesir tahmini TEK KAYNAKTAN gelmeli (kural #11).
        assert res['x_cg_full'] == pytest.approx(
            CG_ASSUMED_FULL_FRACTION * s.aero.L, rel=1e-12)
        assert res['x_cg_empty'] == pytest.approx(
            CG_ASSUMED_EMPTY_FRACTION * s.aero.L, rel=1e-12)

    def test_cg_verilirse_kaynak_supplied(self):
        L = _arac().L
        s = _cozucu(x_cg_full=0.60 * L, x_cg_empty=0.55 * L)
        res = s.solve(t_max=300.0)
        assert res['x_cg_source'] == 'supplied'
        assert res['x_cg_is_estimate'] is False
        assert res['x_cg_full'] == pytest.approx(0.60 * L, rel=1e-12)

    def test_iki_kosum_kunyeden_ayirt_edilebilir(self):
        """Uydurulan ve açıkça verilen AYNI CG artık ayırt edilebilmeli.

        ÖNCE: iki koşum bit-eş çıktı veriyordu (static_margin_full 5,199 ve
        aynı uyarı listesi) — tüketici hükmün uydurulduğunu göremiyordu.
        SONRA: sayılar hâlâ aynı (fizik değişmedi) ama künye AYRIŞIYOR.
        """
        L = _arac().L
        varsayilan = _cozucu().solve(t_max=300.0)
        acik = _cozucu(x_cg_full=0.55 * L, x_cg_empty=0.50 * L
                       ).solve(t_max=300.0)
        # Fizik AYNI kalmalı (onarım sayıyı kaydırmadı, künyeyi ekledi).
        assert varsayilan['static_margin_full'] == pytest.approx(
            acik['static_margin_full'], rel=1e-12)
        assert varsayilan['apogee'] == pytest.approx(acik['apogee'], rel=1e-12)
        # Künye AYRIŞMALI.
        assert varsayilan['x_cg_source'] != acik['x_cg_source']

    def test_kunye_cozucu_coktugunde_de_yayimlanir(self):
        """CG saf geometridir: entegrasyon çökse de künye None'a çevrilmez."""
        s = _cozucu()
        res = s.solve(t_max=0.5)          # ufuk kısa: apoje bulunamaz
        assert res['x_cg_source'] in ('assumed_length_fraction', 'supplied')
        assert isinstance(res['x_cg_full'], float)


# ===========================================================================
# P4B3-04 — recompute'un eksik girdi ikamesi BEYAN edilir
# ===========================================================================

# V301/T-ÇAPA-A: çekirdek 30 -> 76 mm. a = 0,005 (katalog APCP a'sının
# ~2,24 katı) boğazı büyütür: 30 mm'de A_p/A_t 0,396, tek tanımın 48 mm'sinde
# 0,958 (ikisi de K-A port kapısından 422). 76 mm ölçülen A_p/A_t 2,218
# (tests/test_faz4_motor_kapilari.KATI_TABAN ile aynı ölçüm). Konu ikame
# künyesidir, boğulan port değil (kural 1).
KATI_TAM_PROJE = {
    'grain_type': 'bates', 'propellant_type': 'apcp',
    'chamber_diameter': 100, 'grain_length': 500,
    'core_diameter': 76, 'chamber_pressure': 40,
    'burn_rate_a': 0.005, 'burn_rate_n': 0.35,
}


def _recompute(fields, motor_type='solid'):
    return fv.recompute_from_project(
        {'motor_type': motor_type, 'inputs': {'fields': dict(fields)}})[1]


class TestIkameKunyesi:
    """Uydurma-veri-yasağının recompute tarafındaki karşılığı."""

    def test_tam_proje_kunye_uretmez(self):
        """Hiçbir ikame yoksa sonuç sözlüğüne DOKUNULMAZ (bit-aynı yol)."""
        res = _recompute(KATI_TAM_PROJE)
        assert fv.SUBSTITUTION_FIELD_KEY not in res
        assert fv.SUBSTITUTION_NOTE_KEY not in res

    def test_bos_proje_ikameyi_ad_ad_soyler(self):
        res = _recompute({})
        adlar = res.get(fv.SUBSTITUTION_FIELD_KEY)
        assert adlar, 'boş projeden tam sonuç geldi ve ikame beyanı yok'
        # Beyan GERÇEK alan adlarını taşır (sayı değil, ad).
        assert set(adlar) == set(KATI_TAM_PROJE), (
            f'ikame listesi eksik/fazla: {sorted(adlar)}')
        assert isinstance(res.get(fv.SUBSTITUTION_NOTE_KEY), str)

    def test_tek_eksik_alan_adiyla_beyan_edilir(self):
        eksik = {k: v for k, v in KATI_TAM_PROJE.items()
                 if k != 'chamber_pressure'}
        res = _recompute(eksik)
        assert res.get(fv.SUBSTITUTION_FIELD_KEY) == ['chamber_pressure']

    def test_bos_string_de_ikame_sayilir(self):
        """Form boş bırakılmışsa ('' değeri) de bir varsayılan KONUYOR."""
        alanlar = dict(KATI_TAM_PROJE, core_diameter='')
        res = _recompute(alanlar)
        assert res.get(fv.SUBSTITUTION_FIELD_KEY) == ['core_diameter']

    def test_kunye_normalize_semasina_sizmaz(self):
        """İkame künyesi SONUÇ sözlüğündedir; araç şemasına anahtar EKLEMEZ.

        Uç sözleşmesi (tests/test_faz6_f5_app.py) araç şemasının DIŞINDA
        anahtar kabul etmiyor; künye o yüzden motor sonucunda taşınır.
        """
        v = fv.normalize('solid', _recompute({}), source='project')
        assert fv.SUBSTITUTION_FIELD_KEY not in v
        assert fv.SUBSTITUTION_NOTE_KEY not in v

    def test_varsayilani_olmayan_alan_ikame_sayilmaz(self):
        """``default is None`` olan alanda sayı İCAT EDİLMİYOR → ikame yok.

        Hibrit kolda ``thrust``/``burn_time`` gibi alanlar motora "verilmedi"
        olarak geçer; onları ikame diye saymak künyeyi gürültüye boğardı.
        """
        eksik = {k: v for k, v in KATI_TAM_PROJE.items()
                 if k != 'chamber_pressure'}
        res = _recompute(eksik)
        adlar = res.get(fv.SUBSTITUTION_FIELD_KEY) or []
        assert 'thrust' not in adlar and 'burn_time' not in adlar


# ===========================================================================
# P4B3-08 / P4B3-19 — hibrit dış çap ve atıl kütle künyesi
# ===========================================================================

def _hibrit(**motor_over):
    motor = {
        'thrust': 5000.0, 'burn_time': 8.0, 'propellant_mass_total': 12.0,
        'chamber_diameter': 0.15,
        'design_summary': {'key_dimensions': {
            'dry_mass_estimate_kg': 3.0, 'total_motor_length_mm': 1200.0}},
    }
    motor.update(motor_over)
    return {'motor': motor}


class TestHibritDisCap:
    def test_cidar_dis_capa_iki_kez_girer(self):
        """Dış çap = iç çap + 2×cidar (kardeş katı kolun anlamı)."""
        ic_mm, cidar_mm = 112.214, 11.709
        v = fv.normalize('hybrid', _hibrit(
            chamber_diameter=ic_mm / 1000.0,
            structural_analysis={'chamber_analysis': {
                'diameter': ic_mm, 'wall_thickness_used_mm': cidar_mm}}))
        assert v['engine_od_m'] == pytest.approx(
            (ic_mm + 2.0 * cidar_mm) / 1000.0, rel=1e-12)

    def test_kalin_cidar_dis_capi_buyutur(self):
        """Cidar süpürmesi: alan gerçekten cidara DUYARLI (donuk değil)."""
        ic_mm = 112.214
        capraz = []
        for cidar_mm in (3.0, 11.709, 20.0):
            v = fv.normalize('hybrid', _hibrit(
                chamber_diameter=ic_mm / 1000.0,
                structural_analysis={'chamber_analysis': {
                    'diameter': ic_mm, 'wall_thickness_used_mm': cidar_mm}}))
            capraz.append(v['engine_od_m'])
        assert capraz[0] < capraz[1] < capraz[2], (
            'dış çap cidara duyarlı değil: '
            + ', '.join(f'{d:.6f}' for d in capraz))

    def test_yapisal_blok_yoksa_cidar_uydurulmaz(self):
        """Cidar bilinmiyorsa bir kalınlık İCAT EDİLMEZ; kamara çapı kalır."""
        v = fv.normalize('hybrid', _hibrit())
        assert v['engine_od_m'] == pytest.approx(0.15, rel=1e-12)

    def test_birim_kapisi_korunur(self):
        """Hibrit ``chamber_diameter`` METRE — ortak /1000 YAPILMAZ."""
        v = fv.normalize('hybrid', _hibrit())
        assert v['engine_od_m'] != pytest.approx(0.15 / 1000.0)
        assert v['engine_od_m'] < 1.5


class TestHibritAtilKunyesi:
    """Künye bir ORAN ilan ediyorsa o oran ÖLÇÜLEBİLİR bir iddiadır."""

    @staticmethod
    def _oran(note):
        m = re.search(r'~?\s*([0-9]*\.?[0-9]+)\s*[x×]\s*propellant',
                      note or '', re.IGNORECASE)
        return float(m.group(1)) if m else None

    def test_kural_gercekten_tutuyorsa_oran_ilan_edilir(self):
        v = fv.normalize('hybrid', _hibrit())      # 3,0 = 0,25 × 12,0
        oran = self._oran(v['engine_inert_mass_note'])
        assert oran == pytest.approx(fv.HYBRID_INERT_RULE_OF_THUMB_RATIO)
        assert v['engine_inert_mass'] == pytest.approx(
            oran * v['propellant_mass'], rel=1e-9)

    @pytest.mark.parametrize('prop, inert', [
        (7.9590, 54.4513),      # ölçülen 3 kN N2O/HTPB (oran 6,84)
        (12.0, 12.0),           # oran 1,0
        (12.0, 0.5),            # oran 0,042
    ])
    def test_kural_tutmuyorsa_oran_ILAN_EDILMEZ(self, prop, inert):
        v = fv.normalize('hybrid', _hibrit(
            propellant_mass_total=prop,
            design_summary={'key_dimensions': {
                'dry_mass_estimate_kg': inert,
                'total_motor_length_mm': 1200.0}}))
        note = v['engine_inert_mass_note']
        assert note, 'künye boş — değer kaynaksız yayımlanıyor'
        oran = self._oran(note)
        assert oran is None or v['engine_inert_mass'] == pytest.approx(
            oran * v['propellant_mass'], rel=0.05), (
            f'künye {oran} × propelan diyor ama yayımlanan {inert}: ' + note)

    def test_kunye_motorun_kendi_beyanini_tasir(self):
        """Motor ``dry_mass_basis`` yazdıysa künye onu KAYBETMEZ."""
        basis = 'structural_analysis.weight_analysis.total_weight (test)'
        v = fv.normalize('hybrid', _hibrit(
            propellant_mass_total=7.9590,
            design_summary={'key_dimensions': {
                'dry_mass_estimate_kg': 54.4513,
                'total_motor_length_mm': 1200.0,
                'dry_mass_basis': basis}}))
        assert basis in v['engine_inert_mass_note']

    def test_atil_kutle_yoksa_kunye_bunu_soyler(self):
        v = fv.normalize('hybrid', _hibrit(
            design_summary={'key_dimensions': {
                'total_motor_length_mm': 1200.0}}))
        assert v['engine_inert_mass'] is None
        assert v['engine_inert_mass_note']       # sessiz None değil


# ===========================================================================
# P4B3-09 / P4B3-20 — sıvı toplam boy ve uçan atıl kütle
# ===========================================================================

def _sivi(**over):
    r = {
        'thrust': 10000.0, 'burn_time': 300.0, 'chamber_diameter': 99.2,
        'engine_mass_estimate': 43.5,
        'feed_system': {'total_mass': 18.0},
        'design_summary': {
            'masses': {'propellant_mass_kg': 1025.0, 'engine_mass_kg': 43.5},
            'key_dimensions': {'overall_length_mm': 209.0}},
    }
    r.update(over)
    return r


class TestSiviToplamBoy:
    def test_tam_toplam_kisayi_yener(self):
        """İki kaynak varsa yakınsak bölümü İÇEREN toplam seçilir."""
        tam_m = 0.2708577429354722
        v = fv.normalize('liquid', _sivi(component_sizing={
            'component_dimensions': {'overall_length': tam_m}}))
        assert v['engine_length_m'] == pytest.approx(tam_m, rel=1e-12)

    def test_tek_kaynakta_mm_cevrimi_korunur(self):
        v = fv.normalize('liquid', _sivi())
        assert v['engine_length_m'] == pytest.approx(0.209, rel=1e-12)

    def test_bileşen_toplami_metre_olarak_okunur(self):
        """``component_dimensions.overall_length`` METREDİR — /1000 YAPILMAZ."""
        v = fv.normalize('liquid', _sivi(component_sizing={
            'component_dimensions': {'overall_length': 0.35}}))
        assert v['engine_length_m'] == pytest.approx(0.35, rel=1e-12)

    def test_hicbir_kaynak_yoksa_none(self):
        r = _sivi()
        r['design_summary']['key_dimensions'].pop('overall_length_mm')
        assert fv.normalize('liquid', r)['engine_length_m'] is None


class TestSiviAtilKutle:
    def test_tank_ve_artik_propelan_sayilir(self):
        motor, tank = 43.50319619781663, 77.95481798301827
        nominal, yuklenen = 1025.28430345157, 1179.0769489693052
        r = _sivi(propellant_tanks={'system_summary': {
            'total_tank_mass': tank,
            'total_propellant_mass': yuklenen,
            'total_propellant_mass_nominal': nominal}})
        r['design_summary']['masses']['engine_mass_kg'] = motor
        v = fv.normalize('liquid', r)
        assert v['engine_inert_mass'] == pytest.approx(
            motor + tank + (yuklenen - nominal), rel=1e-12)
        note = (v['engine_inert_mass_note'] or '').lower()
        assert 'tank' in note

    def test_tank_yoksa_disarida_kaldigi_soylenir(self):
        v = fv.normalize('liquid', _sivi())
        note = v['engine_inert_mass_note']
        assert note and 'tank' in note.lower(), (
            'tank kütlesi dışarıda kaldığı hâlde künye sessiz')
        # Sayı DEĞİŞMEZ: eksik alan uydurulmaz.
        assert v['engine_inert_mass'] == pytest.approx(43.5, rel=1e-12)

    def test_besleme_alt_kumesi_atil_kutle_degildir(self):
        """Son çare ``feed_system.total_mass`` yalnız motor kütlesi YOKKEN."""
        r = _sivi()
        r['design_summary']['masses'].pop('engine_mass_kg')
        r.pop('engine_mass_estimate')
        v = fv.normalize('liquid', r)
        assert v['engine_inert_mass'] == pytest.approx(18.0, rel=1e-12)

    def test_rezerv_negatifse_eklenmez(self):
        """Nominal > yüklenen (tutarsız yanıt) → uydurma negatif kütle YOK."""
        r = _sivi(propellant_tanks={'system_summary': {
            'total_tank_mass': 10.0,
            'total_propellant_mass': 100.0,
            'total_propellant_mass_nominal': 200.0}})
        v = fv.normalize('liquid', r)
        assert v['engine_inert_mass'] == pytest.approx(43.5 + 10.0, rel=1e-12)

    def test_motor_kutlesi_yoksa_kunye_fail_closed(self):
        r = _sivi()
        r['design_summary']['masses'].pop('engine_mass_kg')
        r.pop('engine_mass_estimate')
        r.pop('feed_system')
        v = fv.normalize('liquid', r)
        assert v['engine_inert_mass'] is None
        assert v['engine_inert_mass_note']


# ===========================================================================
# EKRAN AYAĞI — launch_site.html künyeyi modülden basar, rakımı gönderir
# ===========================================================================

class TestEkranAyagi:
    @pytest.fixture(scope='class')
    def html(self):
        return LAUNCH_SITE_HTML.read_text(encoding='utf-8')

    def test_atil_kutle_kunyesi_modulden_basilir(self, html):
        """Ekran SABİT cümle değil, normalize'ın ürettiği künyeyi basmalı."""
        assert 'engine_inert_mass_note' in html, (
            'şablon modülün atıl kütle künyesini hiç okumuyor — ekranda '
            'yine sabit bir oran cümlesi kalır (P4B3-19/P4B3-20)')

    def test_saha_rakimi_cozucuye_gonderilir(self, html):
        """Sayfa saha rakımını 6-DOF isteğine koymalı (P4B3-01 ekran ayağı)."""
        assert 'launch_altitude' in html, (
            'saha çözümünden gelen rakım 6-DOF isteğine konmuyor; uçuş '
            'deniz seviyesinde hesaplanır')
        assert '_siteElevM' in html, 'rakım gerçek saha çözümünden gelmiyor'

    def test_enlem_kablosu_korunur(self, html):
        """Regresyon: Coriolis enlemi hâlâ gönderiliyor (v2.6.2 kapısı)."""
        assert 'latitude_deg: la' in html
