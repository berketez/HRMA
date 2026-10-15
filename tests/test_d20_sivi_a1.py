"""ÖH Dalga-20 · sıvı kulvarı a1 — mutasyon kanıtlı bekçiler.

Ölçüm: ``docs/scofield/raw/OH/D20/sivi/a1/once.json`` ⟷ ``sonra.json``
(betik ``olcum.py``); ters mutasyonlar ``mutasyon.py`` / ``mutasyon.json``.

**P3B2-09 (Fable-D18 ŞARTI md. 1-2)** — kullanıcı ε'lu lülede çıkış basıncı
çözülemediğinde ``pe_fixed = P_atm_bar`` yazılıyordu. Ölçüldü
(``once.json`` ``P3B2-09.cf_at_dustugunde``): ``_cf_at`` düşürüldüğünde
``P_e = 1,01325 bar`` — hiçbir şey çözülmemişken lüle tam olarak "ortamla
eşlenik" görünüyordu. Artık ``P_e = NaN`` ve hüküm
``nozzle_angles.exit_pressure_status`` alanında. Yedek (kaba yaklaşım)
dalındaki ``max(4, min(eps, 300))`` eşikleri tek tanımlı sabitlere
(``EXPANSION_RATIO_FALLBACK_MIN/MAX``) alındı ve kırpma o dalda da
``expansion_ratio_clamp`` ile yayımlanıyor.

**P3B2-11 (Fable-D18 ŞARTI)** — ısı döngüsünün istasyon profili artık
ÜRÜNDE: ``cooling_system.nozzle_station_profile``. Bekçi her istasyonu
modülün kendi ``_isentropic_static_temperature`` çözücüsüyle rel=1e-9
karşılaştırır; çıkış düzlemi istasyonu ŞART'ın istediği
``(T_c, ε_çıkış, γ, True)`` çağrısıyla ölçülür.

**OH-D17-15** — üst düzeyde ``chamber_diameter`` (mm) ile
``throat_diameter`` (m) yan yana duruyordu, hiçbirinde birim eki yoktu.
Tarihsel adlar korunarak tek birimli (mm) sonekli dörtlü ve birim beyanı
eklendi.

**OH-D18-03** — besleme hattı TEK KOLDU: 6770 kN'da iki hat da 300 mm'e
dayanıp 12,73 / 20,63 m/s (3-8 bandının 1,6-2,6 katı) üretiyor ve tank
basıncı 33,56 bara çıkıyordu. Kol sayısı artık çözülüyor.

**OH-D20-03** — boğaz C_D tablosu ``# RS-25 NASA standard`` gibi BELGESİZ
atıflar taşıyordu ve künye bunları "NASA values" diye yayımlıyordu. Sayılar
değişmedi; atıf dürüstleşti (``attribution: 'assumed'``).

**OH-D20-06** — hazne ısı yükünün çarpan çarpan kapanışı yayımlanıyor.

**OH-D19-12 (kapanış bekçisi)** — ``UnsupportedInjectorTypeError``in genel
``except``e yutulması D19'da (P3B1-12) kapatılmıştı ama bu ağaçta bekçisi
yoktu; sessiz geri dönüşü engellenir.
"""

import contextlib
import io
import math
import os
import tempfile

import pytest

from hrma.engines.liquid_rocket_engine import (
    EXPANSION_RATIO_FALLBACK_MAX,
    EXPANSION_RATIO_FALLBACK_MIN,
    EXPANSION_RATIO_SOLVER_MAX,
    EXPANSION_RATIO_SOLVER_MIN,
    FEED_LINE_MAX_PARALLEL,
    FEED_LINE_MAX_VELOCITY_MS,
    FEED_LINE_MIN_VELOCITY_MS,
    LiquidRocketEngine,
    UnsupportedInjectorTypeError,
)

TABAN_YUK = {
    'motor_name': 'D20-SIVI', 'thrust': 25000.0, 'burn_time': 30.0,
    'chamber_pressure': 60.0, 'mixture_ratio': 2.3,
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'nozzle_type': 'bell_80',
    'cooling_type': 'regenerative',
}

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOTOR_KAYNAK = os.path.join(KOK, 'hrma', 'engines', 'liquid_rocket_engine.py')


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    os.environ.setdefault('HRMA_USER_DATA_DIR',
                          tempfile.mkdtemp(prefix='hrma-d20-sivi-'))
    os.environ.setdefault('HRMA_HEADLESS', '1')
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _cagir(istemci, yuk):
    r = _sessiz(istemci.post, '/calculate_liquid', json=yuk)
    try:
        j = r.get_json()
    except Exception:                                   # pragma: no cover
        j = None
    return r.status_code, (j if isinstance(j, dict) else {})


@pytest.fixture(scope='module')
def taban(istemci):
    st, j = _cagir(istemci, dict(TABAN_YUK))
    assert st == 200, f'taban koşusu HTTP {st}'
    return j


@pytest.fixture(scope='module')
def f1_olcegi(istemci):
    """F-1 sınıfı (6770 kN) — tek hat modelinin çöktüğü ölçek."""
    st, j = _cagir(istemci, dict(TABAN_YUK, thrust=6770000.0,
                                 chamber_pressure=70.0, mixture_ratio=2.27,
                                 feed_system_type='pump_fed'))
    assert st == 200, f'F-1 ölçeği koşusu HTTP {st}'
    return j


def _iz(d, *yol):
    for k in yol:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _motor(**kw):
    ov = dict(kw.pop('overrides', {}) or {})
    return LiquidRocketEngine(overrides=ov, **kw)


# =========================================================== P3B2-09 (ŞART)
class TestP3B209:
    """Çıkış basıncı çözülemezse ORTAM BASINCI yayımlanmaz (fail-closed)."""

    def test_cf_at_duserse_cikis_basinci_p_atm_olmaz(self, monkeypatch):
        """ŞART md. 1: `_cf_at` başarısızsa P_e'ye P_atm BIRAKILMAZ.

        Ölçülen taban davranışı: P_e = 1,01325 bar (P_atm ile bit-aynı).
        """
        e = _motor(thrust=25000, chamber_pressure=60.0, mixture_ratio=2.3,
                   fuel_type='rp1', oxidizer_type='lox',
                   overrides={'nozzle_expansion_ratio': 12.0})
        _sessiz(e.calculate_performance)

        def _patlat(self, *a, **kw):
            raise RuntimeError('cf_at cokertildi (bekci)')

        monkeypatch.setattr(LiquidRocketEngine, '_cf_at', _patlat)
        e2 = _motor(thrust=25000, chamber_pressure=60.0, mixture_ratio=2.3,
                    fuel_type='rp1', oxidizer_type='lox',
                    overrides={'nozzle_expansion_ratio': 12.0})
        _sessiz(e2.calculate_nozzle_geometry, 0)
        assert math.isnan(float(e2.P_e)), (
            'çıkış basıncı çözülemedi ama sayı yayımlandı: '
            f'P_e={e2.P_e!r} (ortam basıncı 1,01325 bar)')
        assert getattr(e2, '_exit_pressure_unsolved', None), (
            'çözülemedi hükmü kaydedilmedi')

    def test_saglikli_kosuda_cikis_basinci_cozulmus_beyan_edilir(self, taban):
        assert _iz(taban, 'nozzle_angles', 'exit_pressure_status') == 'SOLVED'
        pe = _iz(taban, 'nozzle_angles', 'exit_pressure_bar')
        assert isinstance(pe, (int, float)) and pe > 0

    def test_kullanici_epsilonunda_cikis_basinci_cozulur(self, istemci):
        """Sabit ε'lu lülede pe != pa'dır; çözüm ortam ATAMASI değildir."""
        st, j = _cagir(istemci, dict(TABAN_YUK, nozzle_expansion_ratio=12.0))
        assert st == 200
        na = j.get('nozzle_angles') or {}
        assert na.get('exit_pressure_status') == 'SOLVED'
        pe = float(na['exit_pressure_bar'])
        assert abs(pe - 1.01325) > 1e-6, (
            'ortam basıncı parmak izi: sabit ε\'lu lülenin çıkış basıncı '
            'P_atm ile bit-aynı')

    def test_yedek_dal_esikleri_tek_tanimli(self):
        """ŞART md. 2: `max(4, min(eps, 300))` satır içi eşikleri kalmadı."""
        with open(MOTOR_KAYNAK, encoding='utf-8') as fh:
            kod = [s for s in fh
                   if not s.lstrip().startswith('#')]
        birlesik = ''.join(kod)
        assert 'max(4, min(epsilon_optimal, 300))' not in birlesik, (
            'yedek dal eşikleri hâlâ satır içi literal')
        assert EXPANSION_RATIO_FALLBACK_MIN == 4.0
        assert EXPANSION_RATIO_FALLBACK_MAX == 300.0

    @pytest.mark.parametrize('lo,hi,eps,beklenen', [
        (EXPANSION_RATIO_FALLBACK_MIN, EXPANSION_RATIO_FALLBACK_MAX,
         2.0, 'floor'),
        (EXPANSION_RATIO_FALLBACK_MIN, EXPANSION_RATIO_FALLBACK_MAX,
         900.0, 'ceiling'),
        (EXPANSION_RATIO_FALLBACK_MIN, EXPANSION_RATIO_FALLBACK_MAX,
         12.0, None),
        (EXPANSION_RATIO_SOLVER_MIN, EXPANSION_RATIO_SOLVER_MAX,
         2.0, 'floor'),
    ])
    def test_kirpma_yardimcisi_olguyu_bildirir(self, lo, hi, eps, beklenen):
        """Kırpma TEK noktadan geçer ve olguyu ADIYLA döndürür."""
        deger, etiket = LiquidRocketEngine._clamp_expansion_ratio(eps, lo, hi)
        assert etiket == beklenen
        assert lo <= deger <= hi

    def test_kirpma_bandi_yayimlanir(self, istemci):
        """Kırpma bağladığında hangi BANDIN bağladığı okunabilir."""
        st, j = _cagir(istemci, dict(TABAN_YUK, thrust=5000.0,
                                     chamber_pressure=10.0))
        assert st == 200
        na = j.get('nozzle_angles') or {}
        assert na.get('expansion_ratio_clamp') == 'floor'
        assert na.get('expansion_ratio_clamp_band') == [
            EXPANSION_RATIO_SOLVER_MIN, EXPANSION_RATIO_SOLVER_MAX]


# =========================================================== P3B2-11 (ŞART)
class TestP3B211:
    """Isı döngüsünün istasyon profili ÜRÜNDE ve izentropik çözücüye bağlı."""

    def test_istasyon_profili_yayimlanir(self, taban):
        prof = _iz(taban, 'cooling_system', 'nozzle_station_profile')
        assert isinstance(prof, list) and len(prof) >= 3, (
            'istasyon profili yayımlanmıyor')
        assert _iz(taban, 'cooling_system', 'nozzle_station_profile_basis')
        for st in prof:
            for alan in ('section', 'area_ratio', 'mach',
                         'static_temperature_K',
                         'adiabatic_wall_temperature_K', 'in_heat_integral'):
                assert alan in st, f'{alan} eksik: {st}'

    def test_her_istasyon_izentropik_cozucuyle_bit_ayni(self, taban, istemci):
        """ŞART: yaprak ⟷ `_isentropic_static_temperature` rel=1e-9."""
        prof = _iz(taban, 'cooling_system', 'nozzle_station_profile')
        gamma = float(taban['gamma'])
        t_c = float(taban['chamber_temperature'])
        assert prof
        for st in prof:
            supersonik = st['section'] in ('divergent', 'exit_plane')
            beklenen, mach = LiquidRocketEngine._isentropic_static_temperature(
                t_c, float(st['area_ratio']), gamma, supersonik)
            assert st['static_temperature_K'] == pytest.approx(
                beklenen, rel=1e-9), (
                f"{st['section']} A/A_t={st['area_ratio']}: yayımlanan "
                f"{st['static_temperature_K']} != izentropik {beklenen}")
            assert st['mach'] == pytest.approx(mach, rel=1e-9)

    def test_cikis_istasyonu_sart_cagrisiyla_olculur(self, taban):
        """ŞART md. (a): çıkış istasyonu (T_c, ε_çıkış, γ, True) ile ölçülür."""
        prof = _iz(taban, 'cooling_system', 'nozzle_station_profile')
        cikis = [s for s in prof if s['section'] == 'exit_plane']
        assert len(cikis) == 1, 'çıkış düzlemi istasyonu yok'
        cikis = cikis[0]
        assert cikis['in_heat_integral'] is False, (
            'sıfır uzunluklu çıkış düzlemi ısı entegraline sokulmuş')
        eps = (float(taban['exit_diameter'])
               / float(taban['throat_diameter'])) ** 2
        beklenen, _m = LiquidRocketEngine._isentropic_static_temperature(
            float(taban['chamber_temperature']), eps, float(taban['gamma']),
            True)
        assert cikis['static_temperature_K'] == pytest.approx(
            beklenen, rel=1e-9)

    def test_yakinsak_koni_subsonik_iraksak_supersonik_kokte(self, taban):
        """Dal BÖLÜMDEN gelir; 'A > A_t' kuralına dönüş yakalanır."""
        prof = _iz(taban, 'cooling_system', 'nozzle_station_profile')
        yak = [s for s in prof if s['section'] == 'convergent']
        irak = [s for s in prof if s['section'] == 'divergent']
        assert yak and irak
        assert all(s['mach'] < 1.0 for s in yak), 'yakınsak konide M >= 1'
        assert all(s['mach'] > 1.0 for s in irak), 'ıraksak konide M <= 1'


# ============================================================== OH-D17-15
class TestOHD1715:
    """Üst düzey geometri: tek birim + sonek, tarihsel adlar beyanlı."""

    def test_sonekli_dortlu_yayimlanir(self, taban):
        for alan in ('chamber_diameter_mm', 'chamber_length_mm',
                     'throat_diameter_mm', 'exit_diameter_mm'):
            assert isinstance(taban.get(alan), (int, float)), f'{alan} yok'

    def test_sonekli_alanlar_tek_birim_ve_tarihsel_adlarla_tutarli(self, taban):
        assert taban['chamber_diameter_mm'] == pytest.approx(
            taban['chamber_diameter'], rel=1e-12)
        assert taban['throat_diameter_mm'] == pytest.approx(
            float(taban['throat_diameter']) * 1000.0, rel=1e-12)
        assert taban['exit_diameter_mm'] == pytest.approx(
            float(taban['exit_diameter']) * 1000.0, rel=1e-12)
        # Tek birimli dörtlü kendi arasında ölçekçe TUTARLI olmalı: dördü de
        # mm ise hazne çapı boğaz çapının birkaç katıdır, 1000 katı değil.
        oran = taban['chamber_diameter_mm'] / taban['throat_diameter_mm']
        assert 1.0 < oran < 20.0, (
            f'sonekli alanlar aynı birimde değil: oran {oran}')

    def test_birim_beyani_tarihsel_adlari_isimle_soyler(self, taban):
        beyan = taban.get('geometry_units') or {}
        assert beyan.get('suffixed_fields_unit') == 'mm'
        eski = beyan.get('legacy_field_units') or {}
        assert eski.get('chamber_diameter') == 'mm'
        assert eski.get('throat_diameter') == 'm'
        assert eski.get('exit_diameter') == 'm'
        assert eski.get('chamber_length') == 'mm'

    def test_daralma_orani_capraz_kapaniyor(self, taban):
        cr = taban.get('contraction_ratio')
        assert isinstance(cr, (int, float))
        assert (taban['chamber_diameter_mm']
                / taban['throat_diameter_mm']) ** 2 == pytest.approx(
                    cr, rel=1e-9)


# ============================================================== OH-D18-03
class TestOHD1803:
    """Besleme hattı: çoklu kol bir tasarım ÇIKTISIDIR."""

    def test_f1_olceginde_kol_sayisi_cozulur(self, f1_olcegi):
        pd = _iz(f1_olcegi, 'feed_system', 'pressure_drops') or {}
        for taraf in ('fuel_line', 'oxidizer_line'):
            hat = pd.get(taraf) or {}
            n = hat.get('n_parallel_lines')
            assert isinstance(n, int) and n >= 2, (
                f'{taraf}: tek kol modeli hâlâ yürürlükte (n={n!r})')
            assert n <= FEED_LINE_MAX_PARALLEL

    def test_f1_olceginde_hiz_banda_girer(self, f1_olcegi):
        pd = _iz(f1_olcegi, 'feed_system', 'pressure_drops') or {}
        for taraf in ('fuel_line', 'oxidizer_line'):
            hat = pd.get(taraf) or {}
            assert hat.get('line_velocity_band_status') == 'within', (
                f"{taraf}: {hat.get('line_velocity_m_s')} m/s hâlâ band dışı")
            v = float(hat['line_velocity_m_s'])
            assert FEED_LINE_MIN_VELOCITY_MS <= v <= FEED_LINE_MAX_VELOCITY_MS

    def test_kol_basina_debi_toplamla_kapanir(self, f1_olcegi):
        pd = _iz(f1_olcegi, 'feed_system', 'pressure_drops') or {}
        for taraf in ('fuel_line', 'oxidizer_line'):
            hat = pd.get(taraf) or {}
            assert (float(hat['per_line_mass_flow_kg_s'])
                    * int(hat['n_parallel_lines'])) == pytest.approx(
                        float(hat['total_mass_flow_kg_s']), rel=1e-12)

    def test_kol_eklemek_yavas_hatti_daha_da_yavaslatmaz(self):
        """Bandın ALTINDAKİ akışta kol eklemek durumu kötüleştirir: n=1.

        Gerileme kapısı: arama tavanı yalnız tek kol bandı ÜSTTEN aştığında
        açılır. Çok küçük debide (merdivenin en küçük borusunda bile hız
        3 m/s'nin altında) kol sayısı 1'de kalmalıdır.
        """
        e = _motor(thrust=500.0, chamber_pressure=20.0, mixture_ratio=2.3,
                   fuel_type='rp1', oxidizer_type='lox')
        _sessiz(e.calculate_performance)
        secim = e._line_diameter_selection(0.02, 'fuel')
        assert secim['band_status'] == 'below'
        assert secim['n_parallel_lines'] == 1, (
            'bandın altındaki akışa paralel kol eklenmiş')

    def test_ana_hat_bloklari_kol_sayisini_soyler(self, f1_olcegi):
        """`feed_lines.*_main.diameter` KOL BAŞINADIR; kol sayısı yanında."""
        fl = _iz(f1_olcegi, 'feed_system', 'feed_lines') or {}
        pd = _iz(f1_olcegi, 'feed_system', 'pressure_drops') or {}
        for hat, dusum in (('oxidizer_main', 'oxidizer_line'),
                           ('fuel_main', 'fuel_line')):
            blok = fl.get(hat) or {}
            assert isinstance(blok.get('n_parallel_lines'), int)
            assert blok['n_parallel_lines'] == (pd.get(dusum) or {}).get(
                'n_parallel_lines'), (
                f'{hat}: kol sayısı basınç düşümü bloğuyla çelişiyor')
            assert 'PER LEG' in str(blok.get('diameter_basis', ''))

    def test_kucuk_motorda_kol_sayisi_banda_gore_secilir(self, taban):
        """25 kN'da da kol sayısı bandın kendisinden gelir, sabit değil."""
        pd = _iz(taban, 'feed_system', 'pressure_drops') or {}
        for taraf in ('fuel_line', 'oxidizer_line'):
            hat = pd.get(taraf) or {}
            if not hat:
                continue
            n = hat.get('n_parallel_lines')
            assert isinstance(n, int) and 1 <= n <= FEED_LINE_MAX_PARALLEL
            assert hat.get('line_velocity_band_status') == 'within', (
                f"{taraf}: {hat.get('line_velocity_m_s')} m/s band dışı")


# ============================================================== OH-D20-03
class TestOHD2003:
    """Boğaz C_D: uydurma belge atfı yok, 'assumed' künyesi var."""

    def test_kunye_atfi_makine_okunur(self, taban):
        kunye = taban.get('throat_discharge_coefficient_source') or {}
        assert kunye.get('attribution') == 'assumed'
        assert kunye.get('value') == pytest.approx(
            float(taban['throat_discharge_coefficient']), rel=1e-12)
        assert 'assumed' in str(kunye.get('basis', '')).lower()

    def test_yayimlanan_kunye_belgesiz_atif_iddia_etmez(self, taban):
        metin = str(taban.get('throat_discharge_coefficient_basis', ''))
        for uydurma in ('RS-25', 'F-1 NASA', 'Raptor class', 'NASA values'):
            assert uydurma not in metin, (
                f'belgesiz atıf hâlâ yayımlanıyor: {uydurma!r}')
        assert 'ASSUMED' in metin or 'assumed' in metin

    def test_tabloda_olmayan_cift_varsayilana_dusunce_beyan_eder(self):
        e = _motor(thrust=25000, chamber_pressure=60.0, mixture_ratio=2.3,
                   fuel_type='ethanol', oxidizer_type='lox')
        deger, kunye = e._throat_discharge_coefficient(with_source=True)
        assert deger == 0.98
        assert kunye['from_table'] is False
        assert kunye['attribution'] == 'assumed'


# ============================================================== OH-D20-06
class TestOHD2006:
    """Hazne ısı yükü: çarpanlar yayımlanır ve sayıyı yeniden üretir."""

    def test_kapanis_carpanlari_yuku_yeniden_uretir(self, taban):
        k = _iz(taban, 'cooling_system', 'chamber_heat_load_closure')
        assert isinstance(k, dict), 'kapanış bloğu yayımlanmıyor'
        yeniden = (k['h_gas_chamber_W_m2K'] * k['driving_delta_T_K']
                   * k['chamber_lateral_area_m2'])
        assert yeniden == pytest.approx(k['chamber_heat_load_W'], rel=1e-9)
        assert k['chamber_heat_load_W'] / 1000.0 == pytest.approx(
            float(_iz(taban, 'cooling_system', 'chamber_heat_load')),
            rel=1e-9)

    def test_bartz_alan_olceklemesi_daralma_oraniyla_kapanir(self, taban):
        k = _iz(taban, 'cooling_system', 'chamber_heat_load_closure')
        cr = float(k['contraction_ratio'])
        assert k['bartz_area_scaling_(At_over_Ac)^0.9'] == pytest.approx(
            (1.0 / cr) ** 0.9, rel=1e-9)
        assert k['h_gas_chamber_W_m2K'] == pytest.approx(
            k['h_gas_throat_W_m2K']
            * k['bartz_area_scaling_(At_over_Ac)^0.9']
            * k['sigma_ratio_chamber_over_throat'], rel=1e-9)


# ======================================================= OH-D19-12 (kapanış)
class TestOHD1912:
    """Tanınmayan enjektör tipi genel `except`e YUTULMAZ (D19'da kapandı)."""

    def test_motor_katmani_taninmayan_tipte_yukselir(self):
        e = _motor(thrust=25000, chamber_pressure=60.0, mixture_ratio=2.3,
                   fuel_type='rp1', oxidizer_type='lox',
                   injector_type='banana')
        with pytest.raises(UnsupportedInjectorTypeError):
            _sessiz(e.calculate_performance)

    def test_uc_adli_retle_kapatir(self, istemci):
        st, j = _cagir(istemci, dict(TABAN_YUK, injector_type='banana'))
        assert st == 422
        assert j.get('error') == 'unsupported_injector_type'
