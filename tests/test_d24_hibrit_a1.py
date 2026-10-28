# -*- coding: utf-8 -*-
"""ÖH D24 / hibrit a1 bekçileri.

Kapsanan kalemler
-----------------
OH-D23-18  Hibrit motorun KENDİ çıktısı ile kendi impuls bütçesi çelişiyordu:
           ``isp`` (tasarım ANI, CF·c*/g0) ile
           ``total_impulse / (propellant_mass_total · g0)`` aynı yanıtta
           %1,2028 ayrışıyor (O/F = 1,0) ve yörünge çözücüsünün fail-closed
           kapısı o kolda ``/calculate`` yörüngesini ADIYLA "hesaplanamadı"
           yapıyordu. Motor artık teslim edilen ortalama Isp'yi kendi adıyla
           yayımlıyor ve dinamiğe o giriyor.

P15B2-03   Üç motorun uzunluk birimi tipe göre okunuyordu; hibritte
           ``motor_geometry`` bloğu HİÇ YOKTU. Blok geldi; uçan-araç
           köprüsü birim çıkarımını üreticinin BEYANINA bağladı.

Ölçüm kanıtı: docs/scofield/raw/OH/D24/hibrit/a1/{once,sonra}.json
"""
import math

import pytest

from hrma.analysis.trajectory_analysis import TRAJECTORY_PROPELLANT_REL_TOL
from hrma.constants import G_0

HIBRIT_YUK = {
    'thrust': 1000, 'burn_time': 10, 'of_ratio': 1.0,
    'chamber_pressure': 20.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
}

#: V305/C2 (28 Eki) — AYRIŞAN KOL, AÇIKÇA KURULDU.
#:
#: ``HIBRIT_YUK`` (HTPB, O/F 1,0) bekçinin yazıldığı gün iki Isp'yi
#: %1,2151 ayırıyordu; yörünge kapısının bandı
#: (``TRAJECTORY_PROPELLANT_REL_TOL`` = %1) o kolda ``/calculate``
#: yörüngesini düşürüyordu. Ayrışma iki BİLİNÇLİ ürün değişikliğiyle küçüldü
#: (main ilk-ebeveyn zincirinde aynı gövdeyle ölçüldü, docs'suz ağaç;
#: docs/scofield/raw/OH/V305/ci/C2/):
#:   dcb5a762e (21 Eki, B7 — Berke onaylı, hibrit dengeye yoğun faz C(gr)):
#:     O/F 1,0'da c* 919,26 -> 1165,00 m/s, Isp 129,58 -> 162,50 s; yakıtça
#:     zengin uçta Isp(O/F) eğrisi yassılaştı, ayrışma %-1,2151 -> %-0,3086;
#:   74b55500a (26 Eki, H-PANEL, η_c* 0,89 kaynaklı varsayılan):
#:     %-0,3086 -> %-0,2947 (η = %100 ile %-0,3086 aynen kalıyor).
#: O/F 1,0 kolunda artık kapı bandının ALTINDAYIZ: teslim edilen Isp'yi
#: uçurma onarımı geri alınsa bile kapı tetiklenmez, yani o kol bekçinin
#: ölçtüğü olguyu (iki tarif ayrışınca fark sayıyla yayımlanır ve yörünge
#: teslim edileni uçurur) artık sınamıyor.
#:
#: Ayrışan kol: kaynaklı regresyon yasası n = 0,62 olan parafin
#: (Karabeyoglu ve ark. 2004; Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2;
#: ``HYBRID_REGRESSION_COEFFICIENTS['paraffin']``). Tek dairesel portta
#: ṁ_f ∝ D^(1-2n) = D^-0,24: port açıldıkça yakıt debisi düşer, O/F
#: 2,0 -> 2,43 kayar (ÖLÇÜLDÜ, ``of_shift.regulated``). Elle yasa yok, sayı
#: uydurulmadı. Ölçülen ayrışma %-2,1352 (Isp 170,008 ⟷ teslim 173,718 s),
#: kapı bandının iki katından fazla.
AYRISAN_YUK = dict(HIBRIT_YUK, fuel_type='paraffin', of_ratio=2.0)


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def hibrit_yanit(istemci):
    """O/F = 1,0 — tabanda yörüngeyi düşüren kol (once.json A_OH_D23_18)."""
    r = istemci.post('/calculate', json=HIBRIT_YUK)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def hibrit_motor(hibrit_yanit):
    m = hibrit_yanit.get('motor')
    assert isinstance(m, dict)
    return m


@pytest.fixture(scope='module')
def ayrisan_yanit(istemci):
    """İki Isp'nin kapı bandının ÜSTÜNDE ayrıştığı kol (``AYRISAN_YUK``)."""
    r = istemci.post('/calculate', json=AYRISAN_YUK)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def ayrisan_motor(ayrisan_yanit):
    m = ayrisan_yanit.get('motor')
    assert isinstance(m, dict)
    return m


# ---------------------------------------------------------------------------
# OH-D23-18 — motorun kendi bütçesi
# ---------------------------------------------------------------------------
class TestOHD2318TeslimEdilenIsp:

    def test_teslim_edilen_isp_yayimlaniyor(self, hibrit_motor):
        """Tabanda alan HİÇ YOKTU (once.json: isp_delivered_avg_s = null)."""
        v = hibrit_motor.get('isp_delivered_avg_s')
        assert isinstance(v, float) and math.isfinite(v) and v > 0.0, (
            'motor kendi impuls bütçesinden türeyen Isp\'yi yayımlamıyor: '
            f'{v!r}')

    def test_ozdeslik_TAM_kapaniyor(self, hibrit_motor):
        """I = Isp·m·g0 özdeşliği yayımlanan alanlar üstünde BİREBİR tutmalı.

        Yörünge çözücüsü tam bu işlemi yapıyor; bir bit kayarsa kapı yine
        "iki tarif" der. Bu yüzden yaklaşıklık DEĞİL, eşitlik sınanır.
        """
        i_teslim = hibrit_motor['total_impulse_delivered_Ns']
        m_p = hibrit_motor['propellant_mass_total']
        assert hibrit_motor['isp_delivered_avg_s'] == i_teslim / (m_p * G_0)

    def test_mansetteki_isp_TASARIM_NOKTASI_olarak_kaliyor(self, hibrit_motor):
        """Manşet kümesi (thrust, mdot_total, c*, CF, isp) bozulmadı."""
        beklenen = hibrit_motor['cf'] * hibrit_motor['c_star'] / G_0
        assert hibrit_motor['isp'] == pytest.approx(beklenen, rel=1e-12), (
            'manşet Isp tasarım noktası kümesinden koptu')

    def test_iki_isp_farki_SAYIYLA_yayimlaniyor(self, ayrisan_motor):
        """Fark gizlenmiyor: yüzdesi alanla bildiriliyor.

        V305/C2: kol ``AYRISAN_YUK`` (gerekçe tanımının yanında); ölçülen
        %-2,1352. Eşik yörünge kapısının KENDİ bandıdır (eskiden literal 1,0).
        """
        sapma = ayrisan_motor.get('isp_design_point_delta_pct')
        assert isinstance(sapma, float) and math.isfinite(sapma)
        beklenen = (ayrisan_motor['isp']
                    / ayrisan_motor['isp_delivered_avg_s'] - 1.0) * 100.0
        assert sapma == pytest.approx(beklenen, rel=1e-12)
        assert abs(sapma) > TRAJECTORY_PROPELLANT_REL_TOL * 100.0, (
            'bu koşuda ayrışma yörünge kapısının bandının ÜSTÜNDE olmalıydı; '
            'yük değiştiyse bekçinin ölçtüğü kol da değişmiştir '
            f'(ölçülen %{sapma!r})')

    def test_ayrisan_kolda_yorunge_cozuluyor_ve_teslim_edileni_ucuruyor(
            self, ayrisan_yanit, ayrisan_motor):
        """V305/C2: ``test_yorunge_ARTIK_cozuluyor`` sorusu AYRIŞAN kolda.

        O/F 1,0 kolu kapı bandının altına indiği için onarım geri alınsa da
        orada yörünge çözülür; bu kolda manşet Isp uçurulsaydı kapı
        (``TRAJECTORY_PROPELLANT_REL_TOL``) adıyla reddederdi. Ters mutasyon
        (app.py'de teslim edilen Isp devri kapatıldı): bu test KIRMIZI,
        O/F 1,0 kolundaki ``test_yorunge_ARTIK_cozuluyor`` YEŞİL kaldı.
        """
        tr = ayrisan_yanit.get('trajectory')
        assert isinstance(tr, dict)
        assert 'error' not in tr, tr.get('error')
        assert 'invalid_fields' not in tr
        assert 'trajectory' in tr and 'performance' in tr
        assert tr['flown_isp_s'] == ayrisan_motor['isp_delivered_avg_s']
        assert tr['flown_isp_s'] != ayrisan_motor['isp']

    def test_egrinin_harcadigi_kutle_de_yayimlaniyor(self, hibrit_motor):
        """``isp_delivered_avg_basis`` bu alanın adını anıyor; alan olmalı."""
        m_harcanan = hibrit_motor.get('propellant_mass_consumed_kg')
        assert isinstance(m_harcanan, float) and m_harcanan > 0.0
        assert 'propellant_mass_consumed_kg' in \
            hibrit_motor['isp_delivered_avg_basis']

    def test_yorunge_ARTIK_cozuluyor(self, hibrit_yanit):
        """Tabanda bu kol 'hesaplanamadı' idi (once.json trajectory_error)."""
        tr = hibrit_yanit.get('trajectory')
        assert isinstance(tr, dict)
        assert 'error' not in tr, tr.get('error')
        assert 'invalid_fields' not in tr
        assert 'trajectory' in tr and 'performance' in tr

    def test_ucan_isp_TESLIM_EDILEN(self, hibrit_yanit, hibrit_motor):
        """Yörünge teslim edilen Isp ile entegre edilir ve bunu SÖYLER."""
        tr = hibrit_yanit['trajectory']
        assert tr['flown_isp_s'] == hibrit_motor['isp_delivered_avg_s']
        assert 'isp_delivered_avg_s' in tr['flown_isp_basis']

    def test_yanki_kanonik_motorla_BIT_AYNI_kalir(self, hibrit_yanit,
                                                  hibrit_motor):
        """P-5 yankı sözleşmesi bozulmamalı (test_field_wiring_layer_b
        ``test_motor_echo_copies_never_diverge`` bunu ayrıca ölçer).

        Uçurulan Isp yankının İÇİNE yazılsaydı ``trajectory.motor_data.isp``
        kanonik ``motor.isp``den ayrışırdı — 'bayat/varsayılan kopya' sınıfı.
        """
        md = hibrit_yanit['trajectory']['motor_data']
        assert md['isp'] == hibrit_motor['isp']
        assert md['total_impulse'] == hibrit_motor['total_impulse']
        assert md.get('fuel_type') == 'htpb'
        assert 'isp_headline_design_point_s' not in md


# ---------------------------------------------------------------------------
# P15B2-03 — birim beyanı ve normalize geometri bloğu
# ---------------------------------------------------------------------------
class TestP15B203BirimBeyani:

    def test_hibritte_motor_geometry_blogu_var(self, hibrit_motor):
        """Tabanda blok HİÇ YOKTU (once.json B: motor_geometry_var=false)."""
        geo = hibrit_motor.get('motor_geometry')
        assert isinstance(geo, dict) and geo
        assert geo.get('length_units') == 'm', (
            'blok birimini BEYAN etmiyor — kalemin adını verdiği '
            '"length_units = None" hâli')

    def test_blok_metre_ve_ham_deger_AYNI(self, hibrit_motor):
        """Hibrit zaten metre yayımlıyor; blok 1000'e BÖLMEMELİ."""
        geo = hibrit_motor['motor_geometry']
        for alan in ('chamber_diameter', 'throat_diameter', 'exit_diameter',
                     'chamber_length', 'grain_length'):
            assert geo[alan] == hibrit_motor[alan], alan

    def test_birim_otoritesi_blogu_SI_GARANTILI_okuyor(self, hibrit_motor):
        from hrma.export.motor_geometry import resolve_length_m
        deger, kaynak = resolve_length_m(hibrit_motor, 'chamber_diameter')
        assert kaynak == 'motor_geometry'
        assert deger == hibrit_motor['chamber_diameter']

    def test_cozulemeyen_alan_ADIYLA_beyan_edilir(self):
        from hrma.export.motor_geometry import hybrid_results_to_motor_geometry
        g = hybrid_results_to_motor_geometry({})
        sayilar = {k: v for k, v in g.items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)}
        assert sayilar == {}, f'boş sözlükten sayı üretildi: {sayilar}'
        beyan = g.get('geometry_unresolved')
        assert isinstance(beyan, dict) and beyan
        for alan in ('chamber_diameter', 'chamber_length', 'throat_diameter',
                     'exit_diameter', 'grain_length',
                     'port_diameter_initial'):
            assert alan in beyan and 'looked at' in beyan[alan], alan


class TestP15B203UcanAracKoprusu:
    """Uçan-araç köprüsü birimi TİPTEN değil, BEYANDAN kazanır."""

    HAM = {'chamber_diameter': 0.12, 'thrust': 1000.0, 'burn_time': 10.0}

    def _coz(self, tip, **ek):
        from hrma.analysis import flight_vehicle as fv
        d = dict(self.HAM)
        d.update(ek)
        yuk = {'motor': d} if tip == 'hybrid' else d
        return fv.normalize(tip, yuk)

    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    def test_metre_beyani_1000E_BOLUNMEZ(self, tip):
        v = self._coz(tip, length_units='m')
        assert v['engine_od_m'] == pytest.approx(0.12, rel=1e-12)
        assert v['engine_od_unit_source'] == 'declared:m'

    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    def test_mm_beyani_1000E_BOLUNUR(self, tip):
        """Tabanda hibrit kolu beyanı hiç okumuyordu: 'mm' derken de 0,12 m
        döndürüyordu (once.json C2_beyan_mm_hibrit)."""
        v = self._coz(tip, length_units='mm')
        assert v['engine_od_m'] == pytest.approx(0.00012, rel=1e-12)
        assert v['engine_od_unit_source'] == 'declared:mm'

    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    @pytest.mark.parametrize('deger', [-120.0, 0.0])
    def test_fiziksel_olmayan_olcu_SAYI_URETMEZ(self, tip, deger):
        v = self._coz(tip, chamber_diameter=deger, length_units='m')
        assert v['engine_od_m'] is None
        assert v['engine_od_unit_source'] == 'missing'

    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    def test_beyansiz_belirsiz_deger_KAZANILMAZ(self, tip):
        """Beyan yoksa iki-okuma kuralı işler; iki okuma da makulse sayı
        üretilmez (ÖK-16 / P16B4-02 sözleşmesi köprüde de geçerli)."""
        from hrma.export.motor_geometry import UNEARNED_UNIT_SOURCES
        v = self._coz(tip, chamber_diameter=0.5)
        if v['engine_od_m'] is None:
            assert v['engine_od_unit_source'] in (
                UNEARNED_UNIT_SOURCES | {'missing'})
        else:
            # Kazanıldıysa hangi yoldan kazanıldığı SÖYLENMELİ.
            assert v['engine_od_unit_source'] in ('si', 'mm', 'motor_geometry')

    def test_birim_tablosu_KODDAN_KALKTI(self):
        """Modül artık kendi birim sezgisini yazmıyor, otoriteyi çağırıyor."""
        import inspect
        from hrma.analysis import flight_vehicle as fv
        kaynak = inspect.getsource(fv)
        assert 'resolve_length_m' in kaynak
        assert 'from hrma.export.motor_geometry import' in kaynak
