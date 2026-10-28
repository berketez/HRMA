"""ÖH Dalga-30 · kulvar ``app-api-uc`` · aşama 3/3 — bekçiler.

Kapsanan kalemler (hepsi P16 / B3 "boş gövde süpürmesi" ailesi):

  P16B3-09  ``/api/fea/planar-grain`` duvar saati bütçesi (alt iddia; başlık
            P16 hükmü §5.5'te çürütülmüştü, yeniden AÇILMADI)
  P16B3-34  ``/api/analysis/wall-profile`` geçersiz ``gamma`` /
            ``expansion_ratio``
  P16B3-35  ``/api/analysis/combustion-stability`` modsuz gövde
  P16B3-36  ``/api/uncertainty-analysis`` negatif ``seed``
  P16B3-37  ``/api/advanced-analysis`` boş gövde          (tabanda kapalı)
  P16B3-38  501 saplamaları                               (sağlıklı envanter)
  P16B3-39  ``/api/regression-analysis`` boş gövde        (tabanda kapalı)
  P16B3-40  ``/api/solid-monte-carlo`` örnek sayısı + süre
  P16B3-41  ``/api/advanced-performance-analysis`` boş gövde (ÇÜRÜTÜLDÜ)

Ölçüm kanıtı: ``docs/scofield/raw/OH/D30/app-api-uc/a3/once*.json`` ve
``sonra*.json``; ters-mutasyon: aynı dizindeki ``mutasyon.json``.
"""
import contextlib
import io
import json

import pytest
from tests.support.kanit import kanit_gerekli

# V301/T-ÇAPA-A: katı örnek motor geometrisi tek tanımdan (çekirdek
# 30 -> 48 mm). Eski Ø100/500/30 @ 40 bar BATES portu boğuluyordu
# (A_p/A_t 0,947) ve K-A port kapısından 422 alıyor; bu dosyadaki
# düğümlerin konusu boğulan port değil (K-A RAPOR §6, kural 1).
from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_GEOMETRY_MM  # noqa: E402
_CEKIRDEK_MM = SOLID_DEFAULT_GEOMETRY_MM['core_diameter']



@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(istemci, yol, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            r = istemci.post(yol, json=govde)
    return r.status_code, (r.get_json() or {})


def _alanlar(govde):
    return [f.get('field') for f in (govde.get('invalid_fields') or [])]


def _kunye(govde, ad):
    for f in (govde.get('invalid_fields') or []):
        if f.get('field') == ad:
            return f
    raise AssertionError(f'{ad} künyesi yok: {list(govde)}')


# ===========================================================================
# P16B3-09 — /api/fea/planar-grain duvar saati bütçesi
# ===========================================================================
PG_TABAN = {'grain_type': 'bates', 'propellant_type': 'knsb',
            'outer_diameter_mm': 75, 'core_diameter_mm': 25,
            'chamber_pressure_bar': 40, 'grain_length_mm': 150}


class TestP16B309SureButcesi:
    """Eleman bütçesinin yanında SÜRE bütçesi de beyan edilir ve uygulanır.

    P16 hükmü (``H1-hukum.md`` §5.5) başlığı — "varsayılan koşu 274,3 s" —
    228 kat farkla çürütmüştü; burada yeniden açılmıyor. Ayakta kalan alt
    iddia "duvar saati bütçesi yok" idi ve ölçümle doğrulandı: taban a2'de
    üç koşunun hiçbirinde yanıtta ``budget`` sözcüğü geçmiyordu
    (``a3/once.json`` K1 ``butce_sozcugu_gecti = false``).
    """

    def test_limits_blogu_sure_butcesini_beyan_eder(self, istemci):
        kod, g = _post(istemci, '/api/fea/planar-grain', dict(PG_TABAN))
        assert kod == 200, (kod, str(g)[:300])
        limits = (g.get('fea') or {}).get('limits') or g.get('limits') or {}
        assert 'time_budget_s' in limits, (
            'süre bütçesi beyan edilmiyor; eleman bütçesi var, duvar saati '
            f'bütçesi yok (P16B3-09 alt iddiası): {sorted(limits)}')
        assert limits['time_budget_s'] > 0

    def test_butce_TEK_KAYNAKTAN_okunur(self, istemci):
        """Sayı uçta yazılı değil; deponun kurulu bütçesinden gelir."""
        from hrma.app import _SIXDOF_WALL_CLOCK_BUDGET_S
        kod, g = _post(istemci, '/api/fea/planar-grain', dict(PG_TABAN))
        limits = (g.get('fea') or {}).get('limits') or g.get('limits') or {}
        assert limits['time_budget_s'] == _SIXDOF_WALL_CLOCK_BUDGET_S, (
            'bütçe kopyalanmış; Doktrin 4 gereği '
            '_SIXDOF_WALL_CLOCK_BUDGET_S ile aynı olmalı')

    def test_saglikli_kosum_hala_200_ve_alan_uretiyor(self, istemci):
        """ÖK-22: bütçe kapısı meşru koşuyu daraltmadı."""
        kod, g = _post(istemci, '/api/fea/planar-grain', dict(PG_TABAN))
        assert kod == 200
        assert (g.get('fea') or {}).get('mesh') or g.get('mesh'), (
            'bütçe kapısı sağlıklı koşunun mesh alanını düşürdü')

    def test_butce_yolu_kod_duzeyinde_bagli(self, istemci):
        """Kapı gerçekten ``_butce_ile_kos``tan geçiyor (AST ölçüsü).

        Bekçi sayıya değil İLİŞKİYE bakar: uç gövdesinde çözücü çağrısı
        bütçe yardımcısının içinde durmalı.
        """
        import ast
        import inspect

        import hrma.app as _app
        kaynak = inspect.getsource(_app.api_fea_planar_grain)
        agac = ast.parse(inspect.cleandoc(kaynak))
        adlar = {d.func.id for d in ast.walk(agac)
                 if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)}
        assert '_butce_ile_kos' in adlar, (
            'çözücü bütçe yardımcısı olmadan çağrılıyor; süre kapısı '
            'yalnız beyan düzeyinde kalmış olur')


# ===========================================================================
# P16B3-34 — /api/analysis/wall-profile gamma + expansion_ratio
# ===========================================================================
WP_TABAN = {'chamber_pressure': 20, 'chamber_temperature': 3000,
            'chamber_diameter': 0.1, 'chamber_length': 0.5,
            'burn_time': 10, 'mdot_total': 1.0,
            'material': 'steel', 'wall_thickness': 0.005,
            'throat_diameter': 0.03}


def _wp(**ek):
    return dict(WP_TABAN, **ek)


class TestP16B334Gamma:
    """Bant dışı γ ham 500 değil, adıyla 422.

    ÖLÇÜLDÜ (``a3/once.json`` K2 + ``a3/once2.json`` K11, taban a2
    ``294e6559``): γ = 0,5 / 1,04 / 1,68 / 3,0 → **HTTP 500**, gövdede
    yalnız ``error`` + ``status`` (359 B), alan adı yok, bandın kaynağı
    yok. İstemci hatası sunucu arızası diye yayımlanıyordu.
    """

    @pytest.mark.parametrize('deger', [0.5, 1.0, 1.04, 1.68, 3.0])
    def test_bant_disi_gamma_422_ve_adiyla(self, istemci, deger):
        kod, g = _post(istemci, '/api/analysis/wall-profile',
                       _wp(gamma=deger))
        assert kod == 422, (
            f'γ={deger} HTTP {kod} verdi; 422 bekleniyor (500 ise istemci '
            'hatası yine sunucu arızası diye yayımlanıyor)')
        assert 'gamma' in _alanlar(g)
        assert 'wall_profile' not in g, 'reddedilen istekte profil yayımlandı'

    def test_ret_bandi_TEK_KAYNAKTAN_yayimliyor(self, istemci):
        from hrma.analysis.heat_transfer_analysis import (
            GAMMA_BAND_MAX, GAMMA_BAND_MIN)
        kod, g = _post(istemci, '/api/analysis/wall-profile', _wp(gamma=3.0))
        k = _kunye(g, 'gamma')
        assert k['accepted_range'] == [GAMMA_BAND_MIN, GAMMA_BAND_MAX], (
            'yanıttaki bant modülün bandıyla ayrışmış (Doktrin 4)')
        assert k['submitted'] == 3.0
        assert 'GAMMA_BAND' in str(k.get('basis', '')), (
            'ret kaynağını söylemiyor')

    @pytest.mark.parametrize('deger', [1.2, 1.35, 1.66])
    def test_bant_ici_gamma_hala_gecerli(self, istemci, deger):
        """ÖK-22: kapı sağlıklı envanteri daraltmadı."""
        kod, _ = _post(istemci, '/api/analysis/wall-profile',
                       _wp(gamma=deger))
        assert kod == 200, (deger, kod)

    def test_gamma_gercekten_bagli(self, istemci):
        """γ sessizce düşen bir alan değil; hükmü kaydırıyor.

        ÖLÇÜLDÜ (``a3/once3.json`` K16): h_g tepe γ=1,20 → 7153,21 ·
        γ=1,35 → 4918,91 · γ=1,66 → 3505,36. Bu bekçi SAYIYA değil
        SIRALAMAYA bakar (platform float sözleşmesi).
        """
        tepeler = []
        for deger in (1.20, 1.35, 1.66):
            _, g = _post(istemci, '/api/analysis/wall-profile',
                         _wp(gamma=deger))
            h = [v for v in (g['wall_profile']['h_g'] or [])
                 if isinstance(v, (int, float))]
            tepeler.append(max(h))
        assert tepeler[0] > tepeler[1] > tepeler[2], (
            f'γ profili kaydırmıyor (alan düşüyor olabilir): {tepeler}')


class TestP16B334ExpansionRatio:
    """``expansion_ratio <= 1`` sessizce düşürülmez.

    ÖLÇÜLDÜ (``a3/once2.json`` K11, taban a2 ``294e6559``; yanıt sha256'nın
    ilk 16 hanesi): alan hiç gönderilmeyen koşu ile ``0,5`` / ``0,99`` /
    ``1,0`` gönderen üç koşu BİT-AYNI gövde döndürüyordu
    (``9c36e873f95296dd``), üstelik künye "neither exit_diameter nor
    expansion_ratio was supplied" diyordu — gönderilmişti.
    """

    @pytest.mark.parametrize('deger', [0.5, 0.99, 1.0])
    def test_birim_alti_oran_422(self, istemci, deger):
        kod, g = _post(istemci, '/api/analysis/wall-profile',
                       _wp(expansion_ratio=deger))
        assert kod == 422, (
            f'expansion_ratio={deger} HTTP {kod}; sessizce düşürülüyor '
            'olabilir')
        k = _kunye(g, 'expansion_ratio')
        assert k['reason'] == 'must_exceed_unity'
        assert k['submitted'] == deger

    def test_sessiz_dusus_geri_gelmedi(self, istemci):
        """İLİŞKİ bekçisi: reddedilen gövde temiz gövdeyle AYNI olamaz."""
        import hashlib
        with contextlib.redirect_stdout(io.StringIO()):
            temiz = istemci.post('/api/analysis/wall-profile', json=_wp())
            dusuk = istemci.post('/api/analysis/wall-profile',
                                 json=_wp(expansion_ratio=0.5))
        assert hashlib.sha256(temiz.data).hexdigest() != \
            hashlib.sha256(dusuk.data).hexdigest(), (
                'birim altı genleşme oranı gönderen istek, alanı hiç '
                'göndermeyen istekle bit-aynı yanıt aldı — sayı yine '
                'sessizce düşüyor')

    @pytest.mark.parametrize('deger', [2.0, 8.0])
    def test_birim_ustu_oran_hala_kullaniliyor(self, istemci, deger):
        """ÖK-22 + alan GERÇEKTEN bağlı: meşru oran hükmü değiştiriyor."""
        import hashlib
        with contextlib.redirect_stdout(io.StringIO()):
            temiz = istemci.post('/api/analysis/wall-profile', json=_wp())
            r = istemci.post('/api/analysis/wall-profile',
                             json=_wp(expansion_ratio=deger))
        assert r.status_code == 200, (deger, r.status_code)
        assert hashlib.sha256(r.data).hexdigest() != \
            hashlib.sha256(temiz.data).hexdigest(), (
                f'expansion_ratio={deger} çıktıyı değiştirmiyor')

    def test_pozitiflik_kapisi_korunuyor(self, istemci):
        """D29 a1 / P16B3-31 onarımı bozulmadı (0 ve negatif hâlâ 422)."""
        for deger in (0, -4):
            kod, g = _post(istemci, '/api/analysis/wall-profile',
                           _wp(expansion_ratio=deger))
            assert kod == 422, (deger, kod)
            assert 'expansion_ratio' in _alanlar(g)


# ===========================================================================
# P16B3-35 — /api/analysis/combustion-stability modsuz gövde
# ===========================================================================
CS_URL = '/api/analysis/combustion-stability'


class TestP16B335ModsuzGovde:
    """Gönderilmeyen mod "tanınmayan mod" diye anlatılmaz.

    ÖLÇÜLDÜ (``a3/once.json`` K3 + ``a3/once3.json`` K17, taban a2
    ``294e6559``): ``{}`` ve ``{'mode': null}`` → HTTP 400, gövde
    *"Unknown mode **None**. Available: ['chug', 'damping']"* ve gövdedeki
    TEK anahtar ``error``. Python'un ``None`` sözcüğü ürün yüzüne
    basılıyordu ve panel eksik ALANI makine-okur biçimde göremiyordu.
    """

    @pytest.mark.parametrize('govde', [{}, {'mode': None}, {'mode': ''}])
    def test_mod_yoklugu_422_missing_fields(self, istemci, govde):
        kod, g = _post(istemci, CS_URL, govde)
        assert kod == 422, (
            f'{govde} HTTP {kod} verdi; eksik zorunlu girdi bu ucun kendi '
            'sözleşmesinde 422 + missing_fields (aynı fonksiyonun mod içi '
            'kapısı da öyle)')
        assert g.get('missing_fields') == ['mode']
        assert sorted(g.get('supported_modes') or []) == ['chug', 'damping']

    @pytest.mark.parametrize('govde', [{}, {'mode': None}])
    def test_None_sozcugu_kullaniciya_gosterilmiyor(self, istemci, govde):
        with contextlib.redirect_stdout(io.StringIO()):
            r = istemci.post(CS_URL, json=govde)
        metin = r.get_data(as_text=True)
        assert 'None' not in metin, (
            "gönderilmeyen mod hâlâ 'None' diye yankılanıyor: "
            f'{metin[:200]}')

    def test_hukum_uretilmedi(self, istemci):
        kod, g = _post(istemci, CS_URL, {})
        assert 'assessment' not in g and 'nozzle' not in g

    def test_taninmayan_mod_400_KALIR_ve_metni_korunur(self, istemci):
        """Gönderilmiş ama tanınmayan değer eksik girdi DEĞİLDİR.

        Mevcut bekçiler (``test_api_combustion_stability.py``
        ``test_bilinmeyen_mode_400``, ``test_d21_app_api_a1.py``
        ``test_yanma_kararliligi_taninmayan_modda_sayi_uretmez``) bu metni
        okuyor; sözcüğü sözcüğüne korunur, yalnız künye eklendi.
        """
        kod, g = _post(istemci, CS_URL, {'mode': 'screech'})
        assert kod == 400
        assert 'screech' in g['error']
        assert 'chug' in g['error'] and 'damping' in g['error']
        k = _kunye(g, 'mode')
        assert k['reason'] == 'unknown_mode'
        assert sorted(k['accepted_values']) == ['chug', 'damping']

    def test_mod_ici_eksik_alan_sozlesmesi_bozulmadi(self, istemci):
        """ÖK-22: mod verildiğinde eski 422 + missing_fields aynen duruyor."""
        kod, g = _post(istemci, CS_URL, {'mode': 'chug'})
        assert kod == 422
        assert g['mode'] == 'chug'
        assert g['missing_fields']


# ===========================================================================
# P16B3-36 — /api/uncertainty-analysis negatif seed
# ===========================================================================
def _uq(**ek):
    g = {'motor_type': 'hybrid', 'level': 'fast', 'seed': 7, 'n_samples': 12,
         'inputs': {'thrust': 1000.0, 'chamber_pressure': 20.0,
                    'burn_time': 10.0, 'of_ratio': 6.0}}
    g.update(ek)
    return g


class TestP16B336NegatifTohum:
    """Negatif tohumun reddi ucun cümlesiyle çıkar, numpy'ın metniyle değil.

    ÖLÇÜLDÜ (``a3/once3.json`` K15, taban a2 ``294e6559``): ``seed = -1`` →
    HTTP 400, gövde **59 bayt**, tek satır *"expected non-negative
    integer"* — alan adı yok, kaynağı yok. Aynı istekte TİP reddi ise ucun
    kendi cümlesiyle ("Field 'seed' must be an integer.") çıkıyordu.
    """

    @pytest.mark.parametrize('tohum', [-1, -12345])
    def test_negatif_tohum_adiyla_reddedilir(self, istemci, tohum):
        kod, g = _post(istemci, '/api/uncertainty-analysis', _uq(seed=tohum))
        assert kod == 400, (tohum, kod)
        assert 'seed' in _alanlar(g), (
            'ret alan adını taşımıyor; ham kütüphane metni geri gelmiş '
            f'olabilir: {str(g)[:200]}')
        k = _kunye(g, 'seed')
        assert k['reason'] == 'must_be_non_negative'
        assert k['submitted'] == tohum
        assert k['accepted_range'][0] == 0

    def test_ham_kutuphane_metni_yayimlanmiyor(self, istemci):
        with contextlib.redirect_stdout(io.StringIO()):
            r = istemci.post('/api/uncertainty-analysis', json=_uq(seed=-1))
        g = r.get_json() or {}
        assert g.get('error') != 'expected non-negative integer', (
            'numpy metni ham hâliyle hâlâ yayımlanıyor')
        assert "'seed'" in str(g.get('error')), 'ret alanı anmıyor'

    def test_sifir_tohum_GECERLI_kalir(self, istemci):
        """ÖK-22: sıfır meşru bir tohumdur, kapı onu dışlamaz."""
        kod, _ = _post(istemci, '/api/uncertainty-analysis', _uq(seed=0))
        assert kod == 200, kod

    def test_tip_kapisi_korunuyor(self, istemci):
        """D23 a2 / P13B4-12 onarımı bozulmadı."""
        for tohum in (3.7, 'peynir'):
            kod, g = _post(istemci, '/api/uncertainty-analysis',
                           _uq(seed=tohum))
            assert kod == 400, (tohum, kod)
            assert 'integer' in str(g.get('error'))


# ===========================================================================
# P16B3-40 — /api/solid-monte-carlo örnek sayısı + süre bütçesi
# ===========================================================================
MC_TABAN = {'chamber_pressure': 40, 'chamber_diameter': 100,
            'grain_length': 500, 'core_diameter': _CEKIRDEK_MM,
            'propellant_type': 'apcp'}


class TestP16B340OrnekSayisi:
    """Sıfır/negatif örnekten "güvenilirlik" hükmü çıkmaz.

    ÖLÇÜLDÜ (``a3/once2.json`` K13, taban a2 ``294e6559``): ``n_samples``
    **0** ve **-5** → HTTP 200 + tam istatistik bloğu (2781 B, 0,5 s).
    ``n_samples = 100000`` → HTTP 200, **46,7 s**; uçta ne örnek bandı ne
    duvar saati bütçesi vardı.
    """

    @pytest.mark.parametrize('n', [0, -5, 1])
    def test_taban_alti_ornek_422(self, istemci, n):
        kod, g = _post(istemci, '/api/solid-monte-carlo',
                       dict(MC_TABAN, n_samples=n))
        assert kod == 422, (
            f'n_samples={n} HTTP {kod}; örneksiz bir dağılımdan hüküm '
            'yayımlanıyor olabilir')
        k = _kunye(g, 'n_samples')
        assert k['reason'] == 'below_minimum'
        assert 'status' in g and g['status'] == 'error'

    def test_taban_TEK_KAYNAKTAN_okunur(self, istemci):
        from hrma.app import UQ_MIN_SAMPLES
        kod, g = _post(istemci, '/api/solid-monte-carlo',
                       dict(MC_TABAN, n_samples=0))
        k = _kunye(g, 'n_samples')
        assert k['accepted_range'][0] == UQ_MIN_SAMPLES, (
            'taban kopyalanmış; kardeş belirsizlik ucunun sabitiyle aynı '
            'olmalı (Doktrin 4)')

    def test_sayi_olmayan_ornek_sayisi_422(self, istemci):
        kod, g = _post(istemci, '/api/solid-monte-carlo',
                       dict(MC_TABAN, n_samples='peynir'))
        assert kod == 422
        assert 'n_samples' in _alanlar(g)

    def test_varsayilan_ADIYLA_beyan_edilir(self, istemci):
        """Sessiz yedek değil, adı konmuş varsayılan."""
        from hrma.app import SOLID_MC_DEFAULT_SAMPLES
        kod, g = _post(istemci, '/api/solid-monte-carlo', dict(MC_TABAN))
        assert kod == 200, (kod, str(g)[:200])
        assert g['n_samples_source'] == 'endpoint_default'
        assert g['n_samples_requested'] == SOLID_MC_DEFAULT_SAMPLES

    def test_gecerli_ornek_sayisi_hala_kosuyor(self, istemci):
        """ÖK-22: kapı meşru koşuyu daraltmadı."""
        kod, g = _post(istemci, '/api/solid-monte-carlo',
                       dict(MC_TABAN, n_samples=50))
        assert kod == 200, (kod, str(g)[:200])
        assert g['n_samples_source'] == 'request'
        assert g['n_samples_requested'] == 50

    def test_sure_butcesi_kod_duzeyinde_bagli(self, istemci):
        """Koşu ``_butce_ile_kos`` içinden geçiyor (AST ölçüsü).

        Bütçenin kendisi 60 s olduğu için meşru koşuda (ölçülen en kötü
        7,1 s) tetiklenmez; bekçi bu yüzden süre ölçmez, İLİŞKİYİ ölçer.
        """
        import ast
        import inspect

        import hrma.app as _app
        agac = ast.parse(inspect.cleandoc(
            inspect.getsource(_app.solid_monte_carlo)))
        adlar = {d.func.id for d in ast.walk(agac)
                 if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)}
        assert '_butce_ile_kos' in adlar, (
            'Monte Carlo koşusu bütçesiz çağrılıyor')

    def test_butce_TEK_KAYNAKTAN(self):
        import inspect

        import hrma.app as _app
        kaynak = inspect.getsource(_app.solid_monte_carlo)
        assert '_SIXDOF_WALL_CLOCK_BUDGET_S' in kaynak, (
            'bütçe sayısı uca kopyalanmış olabilir (Doktrin 4)')

    def test_bos_govde_kapisi_korunuyor(self, istemci):
        """D15 a1 / P7B2-06 onarımı bozulmadı."""
        kod, g = _post(istemci, '/api/solid-monte-carlo', {})
        assert kod == 422
        assert g['error'] == 'solid_monte_carlo_missing_inputs'


# ===========================================================================
# TABANDA KAPALI / SAĞLIKLI ENVANTER — ÖK-22 kilitleri
# ===========================================================================
class TestTabandaKapaliKalemler:
    """P16B3-37 / -38 / -39 / -40(boş gövde) ölçümle TABANDA kapalı bulundu.

    Ölçüm: ``a3/taban.json`` (dalga tabanı ``ab7cf68b``, ORTAK taban
    ağacında koşuldu) ve ``a3/once.json`` (a2 ağacı) — ikisi de aynı
    sonucu verdi, yani bu dalganın a1/a2 aşamalarının işi değil.
    Bu bekçiler onarımı değil, GERİLEMEMESİNİ kilitler.
    """

    def test_p16b337_advanced_analysis_bos_govde_422(self, istemci):
        """D24 a1 / P7B2-10: boş ``analysis_types`` 'başarılı' değildir."""
        for govde in ({}, {'analysis_types': []},
                      {'analysis_types': ['banana']}):
            kod, g = _post(istemci, '/api/advanced-analysis', govde)
            assert kod == 422, (govde, kod)
            assert g['error'] == 'unsupported_analysis_type'
            assert g['supported_analysis_types']

    def test_p16b339_regression_bos_govde_422(self, istemci):
        """ÖH Z5S / S1 · P16B1-24: 252 sayı yerine adlı ret."""
        for govde in ({}, {'motor_data': {}}):
            kod, g = _post(istemci, '/api/regression-analysis', govde)
            assert kod == 422, (govde, kod)
            assert g['error'] == 'incomplete_regression_input'

    @pytest.mark.parametrize('yol', ['/api/kinetic-analysis',
                                     '/api/professional-analysis',
                                     '/api/cfd-analysis'])
    def test_p16b338_saplamalar_501_ve_sayi_uretmiyor(self, istemci, yol):
        """SAĞLIKLI ENVANTER (ÖK-22): dürüst saplama gevşetilemez."""
        with contextlib.redirect_stdout(io.StringIO()):
            r = istemci.post(yol, json={})
        assert r.status_code == 501, (yol, r.status_code)
        g = r.get_json() or {}
        assert 'rebuilt' in str(g.get('error')), (
            'saplama metni değişmiş; sessiz bir 200 dönmüş olabilir')
        _sayilar = []

        def _gez(x):
            if isinstance(x, dict):
                [_gez(v) for v in x.values()]
            elif isinstance(x, list):
                [_gez(v) for v in x]
            elif isinstance(x, (int, float)) and not isinstance(x, bool):
                _sayilar.append(x)
        _gez(g)
        assert not _sayilar, f'{yol} saplaması sayı basmaya başlamış'


class TestP16B341Curutuldu:
    """``/api/advanced-performance-analysis`` boş gövde — başlık ÇÜRÜTÜLDÜ.

    Kalem "200 + **0 sayı** ama 4,28 s harcıyor — sayı basmıyor, süre
    yiyor" diyordu. ÖLÇÜLDÜ (``a3/once2.json`` K12, taban a2 ``294e6559``;
    ``a3/taban.json`` K9 dalga tabanında AYNI): yanıtın ``plot_data`` alanı
    bir JSON **DİZESİDİR**, içinde **518 sayı** vardır — bulucunun sayacı
    yalnız JSON yapraklarını saydığı için dizeyi 0 görmüştür. Üstelik boş
    gövdede yüzey uydurulmuyor, kimliği figür başlığında BEYAN ediliyor:
    *"N2O / HTPB (reference pair — propellant identity not supplied)"*.
    Süre de israf değil: 49/49 düğümlük kimyasal denge taraması (ilk koşu
    3,2-3,3 s; kimlik verilen ikinci koşu 0,03 s — önbellekli).

    Bu bekçi çürütmeyi kilitler: beyan kaybolursa ya da yüzey kimliksiz
    yayımlanmaya başlarsa kırmızı verir.
    """

    def test_bos_govde_sayi_BASIYOR(self, istemci):
        import re
        kod, g = _post(istemci, '/api/advanced-performance-analysis', {})
        assert kod == 200
        pd = g['plot_data']
        assert isinstance(pd, str), 'plot_data artık dize değil'
        sayilar = re.findall(r'-?\d+\.?\d*(?:[eE][-+]?\d+)?', pd)
        assert len(sayilar) > 100, (
            f'"0 sayı" iddiası: gövdede {len(sayilar)} sayı var')

    def test_kimliksiz_yuzey_REFERANS_CIFT_diye_beyan_edilir(self, istemci):
        kod, g = _post(istemci, '/api/advanced-performance-analysis', {})
        pd = g['plot_data']
        assert 'reference pair' in pd, (
            'kimlik verilmeyen yüzey artık referans çift olduğunu '
            'söylemiyor — uydurma bir motorun yüzeyi gibi görünür')
        assert 'not supplied' in pd

    def test_taninmayan_analysis_type_400_KALIR(self, istemci):
        kod, g = _post(istemci, '/api/advanced-performance-analysis',
                       {'analysis_type': 'peynir'})
        assert kod == 400
        assert 'peynir' in str(g.get('error'))


def test_kanit_dizini_yerinde():
    """Ölçüm dosyaları depoda duruyor (rapor iddiası koda karşı denetlenir)."""
    import pathlib
    kok = pathlib.Path(__file__).resolve().parents[1]
    d = kok / 'docs/scofield/raw/OH/D30/app-api-uc/a3'
    for ad in ('once.json', 'once2.json', 'once3.json', 'taban.json'):
        p = d / ad
        assert kanit_gerekli(p).exists(), f'ölçüm kanıtı yok: {p}'
        json.loads(kanit_gerekli(p).read_text(encoding='utf-8'))
