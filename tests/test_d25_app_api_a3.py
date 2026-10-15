# -*- coding: utf-8 -*-
"""ÖH D25 / app-api aşama-3 bekçisi — P16B1-45 (enjektör kimliği).

Kalem: "``discharge_coefficient`` TEK istekte İKİ tüketiciye: biri kapılı+
beyanlı, diğeri kapısız — plaka geometrisi kapısız olandan".

ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/D25/app-api/a3/once_A.json,
once_BC.json — taban cd896e7):

  * Alan GÖNDERİLMEDİĞİNDE (varsayılan yol) tek /calculate yanıtı AYNI ADLA
    iki sayı yayımlıyordu:
        motor.injector_design.discharge_coefficient = 0,78  (künyeli)
        injector.discharge_coefficient              = 0,70  (künyesiz)
  * Plaka geometrisi (n_holes / hole_diameter / injection_area) ve
    v2.6.26'dan beri CAD-STEP-DXF ikincisinden türüyordu: enjeksiyon alanı
    22,0217 ⟷ 19,7631 mm² (%+11,43), delik çapı 0,93606 ⟷ 0,88676 mm
    (%+5,56).
  * 0,70 ürünün KENDİ beyanına da aykırıydı: ``advanced.html`` alanının
    ``placeholder``ı 0,78 ve ipucu metni "Leave empty to use the solver
    default of 0.78, which is then declared in the results instead of
    being silently assumed" diyor.
  * Plaka bloğundaki 7 büyüklüğün künyesi vardı (yoğunluk, viskozite, σ,
    P_v, ΔP, L/D, plaka kalınlığı); geometriyi doğrudan belirleyen Cd
    künyesizdi.

ONARIM: plaka çözücüsü isteğin ÇÖZÜLMÜŞ Cd'sini alır (tek kaynak) ve
gerekçesiyle yayımlar; çağıran vermediyse sayı devrenin Cd tablosunun
kendi varsayılan orifis tanımından gelir ve KAZANILMAMIŞ olduğu
``discharge_coefficient_earned`` ile durur.
"""
import ast
import contextlib
import io
import os
import re

import pytest

os.environ.setdefault('HRMA_HEADLESS', '1')

from hrma.engines.injector_design import (             # noqa: E402
    CD_TABLE, DEFAULT_ORIFICE_INLET, DEFAULT_ORIFICE_L_OVER_D,
    default_discharge_coefficient, discharge_coefficient,
)
from hrma.utils.injector_design import InjectorDesign  # noqa: E402

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PY = os.path.join(KOK, 'hrma', 'app.py')
UTILS_PY = os.path.join(KOK, 'hrma', 'utils', 'injector_design.py')
ADVANCED = os.path.join(KOK, 'hrma', 'templates', 'advanced.html')

HIBRIT = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'chamber_pressure': 20.0, 'fuel_type': 'htpb',
          'oxidizer_type': 'n2o', 'motor_type': 'hybrid'}


def _yorumsuz(yol):
    """Kaynağın YORUM SATIRLARINDAN arındırılmış hâli.

    Kusurun eski biçimi (``spec.get('inlet_ox', 'sharp')``) belgeleme
    amacıyla yorumlarda AYNEN alıntılanıyor; düz bir metin taraması onu
    yaşayan kod sanardı."""
    satirlar = open(yol, encoding='utf-8').read().splitlines()
    return '\n'.join(s for s in satirlar if not s.lstrip().startswith('#'))


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


def _calculate(istemci, **ek):
    govde = dict(HIBRIT)
    govde.update(ek)
    r = _sessiz(istemci.post, '/calculate', json=govde)
    assert r.status_code == 200, (
        'sağlıklı hibrit gövdesi 200 vermeli, alınan: %s' % r.status_code)
    return r.get_json()


def _iki_blok(j):
    """(plaka bloğu, devre bloğu) — ikisi de aynı yanıttan."""
    plaka = j.get('injector')
    devre = (j.get('motor') or {}).get('injector_design')
    assert isinstance(plaka, dict), 'yanıtta ``injector`` bloğu yok'
    assert isinstance(devre, dict), 'yanıtta ``motor.injector_design`` yok'
    return plaka, devre


@pytest.fixture(scope='module')
def yanit_varsayilan(istemci):
    return _calculate(istemci)


# ---------------------------------------------------------------------------
# 1) Tek istek → tek deşarj katsayısı
# ---------------------------------------------------------------------------
class TestP16B145TekDesarjKatsayisi:

    def test_alan_gonderilmediginde_iki_blok_ayni_cd_yi_yayimlar(
            self, yanit_varsayilan):
        """KUSURUN TA KENDİSİ: 0,70 ⟷ 0,78 ayrışması (once_A.json)."""
        plaka, devre = _iki_blok(yanit_varsayilan)
        assert plaka['discharge_coefficient'] == devre[
            'discharge_coefficient'], (
            'aynı istekte iki farklı Cd yayımlanıyor: plaka=%r devre=%r'
            % (plaka['discharge_coefficient'],
               devre['discharge_coefficient']))

    @pytest.mark.parametrize('cd', [0.70, 0.95, 0.25])
    def test_alan_gonderildiginde_de_ayni(self, istemci, cd):
        plaka, devre = _iki_blok(_calculate(istemci,
                                            discharge_coefficient=cd))
        assert plaka['discharge_coefficient'] == pytest.approx(cd)
        assert devre['discharge_coefficient'] == pytest.approx(cd)

    def test_varsayilan_urunun_kendi_beyaniyla_ayni(self, yanit_varsayilan):
        """Form ``placeholder``ı ve ipucu metni 0,78 diyor; ölçüldü:
        plaka 0,70 yayımlıyordu (once_BC.json B)."""
        metin = open(ADVANCED, encoding='utf-8').read()
        ph = re.search(r'id="discharge_coefficient"[^>]*placeholder="([^"]+)"',
                       metin)
        ipucu = re.search(r'solver default of ([0-9.]+)', metin)
        assert ph and ipucu, 'ürünün Cd beyanı formda bulunamadı'
        beyan = float(ph.group(1))
        assert float(ipucu.group(1)) == beyan
        plaka, _ = _iki_blok(yanit_varsayilan)
        assert plaka['discharge_coefficient'] == pytest.approx(beyan)

    def test_plaka_cd_si_kunyesiyle_yayimlanir(self, yanit_varsayilan):
        plaka, _ = _iki_blok(yanit_varsayilan)
        assert 'discharge_coefficient_basis' in plaka
        assert 'discharge_coefficient_earned' in plaka
        assert isinstance(plaka['discharge_coefficient_basis'], str)
        assert plaka['discharge_coefficient_basis'].strip()

    def test_kunye_envanterinde_cd_artik_yalniz_degil(self, yanit_varsayilan):
        """Ölçüldü (once_BC.json C): plaka bloğunda künyeli 7 büyüklük
        vardı, Cd onlardan biri DEĞİLDİ."""
        plaka, _ = _iki_blok(yanit_varsayilan)
        kokler = {k.rsplit('_', 1)[0] for k in plaka
                  if k.endswith(('_basis', '_source', '_earned'))}
        kokler = set()
        for k in plaka:
            for ek in ('_basis', '_source', '_earned'):
                if k.endswith(ek):
                    kokler.add(k[:-len(ek)])
        assert 'discharge_coefficient' in kokler


# ---------------------------------------------------------------------------
# 2) Kazanılmışlık sözleşmesi (kardeş: plate_thickness / D20-P15B1-02)
# ---------------------------------------------------------------------------
class TestP16B145KazanilmislikSozlesmesi:

    def _plaka(self, **kw):
        varsayilan = dict(mdot_ox=1.2, chamber_pressure=30.0,
                          tank_pressure=55.0, oxidizer_density=786.0,
                          injector_type='showerhead')
        varsayilan.update(kw)
        return _sessiz(InjectorDesign(**varsayilan).calculate)

    def test_cagiran_vermezse_kazanilmamis_ve_beyanli(self):
        r = self._plaka()
        beklenen, _ = default_discharge_coefficient()
        assert r['discharge_coefficient'] == pytest.approx(beklenen)
        assert r['discharge_coefficient_earned'] is False
        assert 'NOT earned' in r['discharge_coefficient_basis']

    def test_cagiran_verirse_kazanilmis_ve_kunyesi_tasinir(self):
        r = self._plaka(discharge_coefficient=0.62,
                        discharge_coefficient_basis='user input (test)')
        assert r['discharge_coefficient'] == pytest.approx(0.62)
        assert r['discharge_coefficient_earned'] is True
        assert r['discharge_coefficient_basis'] == 'user input (test)'

    def test_swirl_de_cd_geometriden_kazanilir(self):
        r = self._plaka(injector_type='swirl')
        assert r['discharge_coefficient_earned'] is True
        assert 'Giffen-Muraszew' in r['discharge_coefficient_basis']

    def test_plaka_alani_cd_ile_ters_orantili(self):
        """Cd geometriyi GERÇEKTEN belirliyor: A = ṁ/(Cd·√(2ρΔP)) →
        A·Cd sabit. Kalemin "plaka geometrisi o sayıdan çıkıyor"
        iddiasının sayısal karşılığı."""
        carpimlar = []
        for cd in (0.50, 0.70, 0.78, 0.95):
            r = self._plaka(discharge_coefficient=cd,
                            discharge_coefficient_basis='test')
            carpimlar.append(r['injection_area'] * cd)
        for c in carpimlar[1:]:
            assert c == pytest.approx(carpimlar[0], rel=1e-9)


# ---------------------------------------------------------------------------
# 3) Tek kaynak (Doktrin 4) — literal geri gelmesin
# ---------------------------------------------------------------------------
class TestP16B145TekKaynak:

    def test_app_py_de_ciplak_0_7_yedegi_yok(self):
        """Kusurun kaynağı ``InjectorDesign(discharge_coefficient=
        data.get('discharge_coefficient', 0.7))`` çağrısıydı. Denetim
        METİNDE değil AĞAÇTA yapılır: kusurun tarihçesi yorum satırlarında
        adıyla anılıyor ve bir metin taraması onu kusur sanardı."""
        agac = ast.parse(open(APP_PY, encoding='utf-8').read())
        cagrilar = [d for d in ast.walk(agac)
                    if isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Name)
                    and d.func.id == 'InjectorDesign']
        assert cagrilar, 'app.py içinde InjectorDesign(...) çağrısı yok'
        for cagri in cagrilar:
            for kw in cagri.keywords:
                if kw.arg != 'discharge_coefficient':
                    continue
                assert isinstance(kw.value, ast.Name), (
                    'Cd yine yerinde üretiliyor (%s) — çözülmüş tek '
                    'kaynaktan gelen bir ad bekleniyordu'
                    % ast.dump(kw.value)[:120])

    def test_plaka_cozucusunun_imza_varsayilani_None(self):
        agac = ast.parse(open(UTILS_PY, encoding='utf-8').read())
        bulundu = False
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.FunctionDef) and dugum.name == '__init__':
                adlar = [a.arg for a in dugum.args.args]
                if 'discharge_coefficient' not in adlar:
                    continue
                bulundu = True
                i = adlar.index('discharge_coefficient')
                kayma = len(adlar) - len(dugum.args.defaults)
                ontanim = dugum.args.defaults[i - kayma]
                assert isinstance(ontanim, ast.Constant) \
                    and ontanim.value is None, (
                    'InjectorDesign.__init__ Cd varsayılanı yine bir sayı: %r'
                    % ast.dump(ontanim))
        assert bulundu, 'InjectorDesign.__init__ bulunamadı'

    def test_devrenin_varsayilan_orifisi_adlandi_ve_tek(self):
        cd, gerekce = default_discharge_coefficient()
        beklenen, beklenen_gerekce = discharge_coefficient(
            DEFAULT_ORIFICE_INLET, DEFAULT_ORIFICE_L_OVER_D)
        assert cd == beklenen and gerekce == beklenen_gerekce
        # Sayı tabloda DURUYOR — ikinci bir yere yazılmadı.
        assert any(t == DEFAULT_ORIFICE_INLET
                   and lo <= DEFAULT_ORIFICE_L_OVER_D < hi
                   and c == cd
                   for t, lo, hi, c, _ in CD_TABLE)

    def test_design_injector_ayni_sabitleri_kullanir(self):
        """``design_injector`` varsayılan orifis tanımını artık literal
        olarak taşımaz. Yorum satırları kusurun eski hâlini alıntılıyor,
        bu yüzden denetim YORUMSUZ kaynak üzerinde yapılır."""
        yol = os.path.join(KOK, 'hrma', 'engines', 'injector_design.py')
        kaynak = _yorumsuz(yol)
        assert "spec.get('inlet_ox', DEFAULT_ORIFICE_INLET)" in kaynak
        assert "spec.get('l_over_d', DEFAULT_ORIFICE_L_OVER_D)" in kaynak
        assert "spec.get('inlet_ox', 'sharp')" not in kaynak
        assert "spec.get('l_over_d', 4.0)" not in kaynak


# ---------------------------------------------------------------------------
# 4) OH-Z5-02 · app-api sahasındaki 5 yaprağın SINIFLANDIRMA ÖNCÜLLERİ
#
# Kalem bu aşamada ENGELLİ kaldı: yaprakların hükmü ölçüldü ama onarımın
# indiği iki dosyadan biri (tests/test_field_wiring_layer_b.py) BU DALGADA
# kardeş ``hibrit`` kulvarı tarafından işleniyor ve orada sayaç eşiği
# ``<= 5`` / ``>= 5`` diye İKİ YÖNLÜ çakılı — kalan 5 tam olarak bu
# yapraklar. Yaprakları tek taraflı düşürmek birleşmede kardeşin
# bekçisini KIRAR (kardeş-dal ölçümü: a3/kardes_dal.txt).
#
# Bu yüzden burada onarım değil, D26'nın tek hamlede kapatabilmesi için
# ÖNCÜLLER kilitlenir: sınıflandırma bir kanaat değil, ölçülen bir olgu
# olsun. Ölçüm: docs/scofield/raw/OH/D25/app-api/a3/once_z5.json.
# ---------------------------------------------------------------------------
class TestOHZ502AppApiYapraklariOnculler:

    def test_uyari_yankisi_beyan_yankisinin_bit_ayni_kopyasidir(
            self, yanit_varsayilan, istemci):
        """``.input_warnings[0].params.submitted``, shake'in ZATEN beyan
        yankısı saydığı ``.inputs_not_used[0].submitted`` yaprağının
        kopyasıdır (app.py:2048 ``beyan.get('submitted')``).

        Ölçüldü (once_z5.json): altı koşuda 6/6 bit-aynı. Öncül budur —
        desen genişletmesi bir kanaat değil, ölçülmüş bir özdeşliktir.
        """
        from tests.support import shake
        j = _calculate(istemci, chamber_temperature=3000)
        uyarilar = j.get('input_warnings') or []
        beyanlar = j.get('inputs_not_used') or []
        if not uyarilar or not beyanlar:
            pytest.skip('bu gövde beyan/uyarı üretmedi')
        a = (uyarilar[0].get('params') or {}).get('submitted')
        b = beyanlar[0].get('submitted')
        assert shake.bit_ayni(a, b), (
            'uyarı yankısı beyan yankısının kopyası değil: %r ⟷ %r'
            % (a, b))
        assert shake.is_declaration_echo('.inputs_not_used[0].submitted')

    def test_basinc_dusus_bandi_kunyesiyle_yayimlanir_ve_tek_kaynak(self):
        """``validation.injector_assessment.pressure_drop_ratio.band``
        yayımlanan bir KABUL BANDIdır: künyesi iki ucunun da nereden
        geldiğini adıyla söyler ve alt ucu merkezî sabitin bit-aynı
        kopyasıdır. Hüküm-13'ün "yayımlanan model eşiği" sınıfı."""
        from tests.support import shake
        from hrma.analysis.acoustic_modes import CHUG_DP_RATIO_MINIMUM
        from hrma.validation.validation_system import ValidationSystem
        vs = ValidationSystem()
        band = vs.injector_limits['pressure_drop_ratio']
        kunye = vs.injector_limit_sources.get('pressure_drop_ratio')
        assert kunye, 'band künyesiz yayımlanıyor'
        assert 'CHUG_DP_RATIO_MINIMUM' in kunye
        assert 'INJECTOR_DP_PC_CEILING' in kunye
        assert shake.bit_ayni(band[0], CHUG_DP_RATIO_MINIMUM), (
            'bandın alt ucu merkezî sabitin kopyası değil — ikinci bir '
            'tanım noktası doğmuş olabilir')
