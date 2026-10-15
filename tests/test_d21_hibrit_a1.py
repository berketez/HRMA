"""ÖH D21 / hibrit kulvarı, aşama 1 — onarım bekçileri.

Kalemler: P15B1-04 (λ tek kaynak + manşet Isp künyesi), P12bB3-02
(desteklenen yakıt kümesi tek kaynak + alan adlı red), OH-D17-10 (γ kabul
bandı tek adlandırılmış sabit), B4-13 (ölü parametre), B4-14 (ölü dal),
B4-15 (ölü kod).

Her bekçi TERS-MUTASYONLA kanıtlanmıştır; kırmızı kanıtı
docs/scofield/raw/OH/D21/hibrit/a1/mutasyon.json içindedir.
"""
import ast
import contextlib
import io
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
YANMA = ROOT / 'hrma' / 'engines' / 'combustion_analysis.py'
ENJEKTOR = ROOT / 'hrma' / 'engines' / 'injector_design.py'
LULE = ROOT / 'hrma' / 'engines' / 'nozzle_design.py'


def _fonksiyon(yol: Path, ad: str):
    agac = ast.parse(yol.read_text(encoding='utf-8'))
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == ad:
            return d
    return None


@pytest.fixture(scope='module')
def istemci():
    ud = os.path.join(tempfile.gettempdir(), 'hrma-d21-hibrit-bekci')
    shutil.rmtree(ud, ignore_errors=True)
    os.makedirs(ud, exist_ok=True)
    os.environ['HRMA_USER_DATA_DIR'] = ud
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _hibrit(istemci, **ek):
    yuk = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
           'chamber_pressure': 20.0, 'fuel_type': 'htpb',
           'oxidizer_type': 'n2o'}
    yuk.update(ek)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = istemci.post('/calculate', json=yuk)
    return r


# =========================================================== P15B1-04
class TestP15B104LambdaTekKaynak:
    """Aynı lülenin diverjans verimi TEK sayı olmalı.

    Ölçüldü (once_lambda.json): manşet zinciri λ'yı katalog sabitinden
    (0,983 / 0,985 / 0,975), lüle paneli konturun kendi açısından okuyordu;
    3 tip × 8 ε = 24 noktanın 24'ü ayrışıyor, en büyük bağıl fark %2,0253.
    Uçtan uca 4 koşumun 4'ünde C_F tutarlılık kapısı out_of_band idi.
    """

    @pytest.mark.parametrize('tip', ['conical', 'bell', 'parabolic'])
    @pytest.mark.parametrize('eps', [2.0, 6.5, 12.0, 40.0, 80.0])
    def test_manset_ve_panel_ayni_lambdayi_okuyor(self, tip, eps):
        from hrma.engines.nozzle_design import NozzleDesigner
        nd = NozzleDesigner()
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            r = nd.design_nozzle(1e-3, eps, 30.0, 1.0, tip)
        panel = float(r['performance']['divergence_efficiency'])
        manset = NozzleDesigner.divergence_efficiency_from_expansion(tip, eps)
        assert manset == pytest.approx(panel, rel=1e-12), (
            'λ iki kaynaktan geliyor: manşet %.12f ⟷ panel %.12f'
            % (manset, panel))

    def test_lambda_genisleme_oranini_goruyor(self):
        """Bell/parabolikte λ ε ile DEĞİŞMELİ (katalog sabiti değişmiyordu)."""
        from hrma.engines.nozzle_design import NozzleDesigner
        degerler = {NozzleDesigner.divergence_efficiency_from_expansion(
            'bell', e) for e in (4.0, 12.0, 40.0, 80.0)}
        assert len(degerler) >= 3, (
            'λ genişleme oranına duyarsız — katalog sabitine geri dönmüş: %s'
            % sorted(degerler))

    def test_uctan_uca_lambda_kapisi(self, istemci):
        r = _hibrit(istemci)
        assert r.status_code == 200
        m = r.get_json()['motor']
        kapi = m['thrust_coefficient_cross_check']
        assert kapi['divergence_efficiencies_identical'] is True
        assert kapi['divergence_efficiency_headline'] == pytest.approx(
            kapi['divergence_efficiency_panel'], rel=1e-12)
        # Adapte genleşmede C_F artık BİT-AYNI: kapı geçmeli.
        assert kapi['status'] == 'pass', kapi['relative_gap_percent']
        # Kapanan kök künyede yaşamaya devam etmesin.
        assert not any('catalogue constant' in c
                       for c in kapi['remaining_causes'])
        # λ'nın kaynağı SESSİZ değil: geometriden mi, yedekten mi geldiği
        # yanıtta yazar (katalog sabitine düşüş beyanlıdır).
        assert m['nozzle_angles']['divergence_efficiency_basis'] == (
            'contour_geometry')

    def test_manset_isp_kendini_tanimliyor(self, istemci):
        """"Hangi sayı teslim edilen?" sorusunun cevabı yanıtta olmalı."""
        r = _hibrit(istemci)
        ozet = r.get_json()['motor']['design_summary']['performance']
        kunye = ozet.get('specific_impulse_basis')
        assert isinstance(kunye, str) and kunye, 'manşet Isp künyesiz'
        assert 'DELIVERED' in kunye
        # Künye rakip yaprakları ADIYLA anmalı (kullanıcı hangisinin ne
        # olduğunu yaprak adını arayarak bulabilsin).
        for ad in ('isp_shifting_s', 'isp_frozen_s',
                   'nozzle_design.performance.specific_impulse'):
            assert ad in kunye, ad


# =========================================================== P12bB3-02
class TestP12bB302YakitKumesi:
    """Desteklenen yakıt kümesi TEK KAYNAK; red MAKİNE-OKUR."""

    def test_liste_ikinci_kez_elle_yazilmamis(self):
        kaynak = YANMA.read_text(encoding='utf-8')
        assert 'htpb, paraffin, pe, pmma, abs, pla, aluminum' not in kaynak, (
            'desteklenen yakıt listesi motor kaynağında ikinci kez yazılı')
        assert re.search(r'^SUPPORTED_HYBRID_FUEL_KEYS\s*=', kaynak, re.M)

    def test_kume_formulu_olan_yakitlarla_ortusuyor(self):
        """Üyelik ölçütü: kimyasal formülü olmayan yakıt kabul edilemez."""
        from hrma.engines.combustion_analysis import (
            CombustionAnalyzer, SUPPORTED_HYBRID_FUEL_KEYS)
        formuller = CombustionAnalyzer._REACTANT_FORMULAS
        eksik = [k for k in SUPPORTED_HYBRID_FUEL_KEYS if k not in formuller]
        assert eksik == [], eksik

    @pytest.mark.parametrize('yakit', ['carbon', 'al2o3', 'mixture', 'custom'])
    def test_desteklenmeyen_yakit_ALAN_ADIYLA_reddediliyor(self, istemci,
                                                           yakit):
        """Ölçüldü: dördü de 400 dönüyordu ve gövdede ``field`` YOKTU.

        ÖH D31 / P12bB3-02 — GEREKÇE ARTIK ADIYLA GELİYOR. Bu testin eski
        hâli ``reason == 'unsupported_fuel_key'`` diye SABİTLİYORDU; yani
        dört anahtarın da aynı genel gerekçeyi almasını KİLİTLİYORDU ve
        kalemin onarımını (kategori hatası / literatür borcu / şema borcu
        ayrımı) kırmızıya düşürüyordu — kusuru koruyan bekçi. Bu testin
        KENDİ iddiası (``field`` ve ``supported_fuels`` gövdede var, red
        400) aynen duruyor; yalnız gerekçe kümesi tek kaynaktan okunuyor.
        """
        from hrma.engines.combustion_analysis import (
            HYBRID_FUEL_REJECTION_REASONS, SUPPORTED_HYBRID_FUEL_KEYS)
        r = _hibrit(istemci, fuel_type=yakit)
        assert r.status_code == 400
        g = r.get_json()
        assert g.get('field') == 'fuel_type', g
        beklenen = HYBRID_FUEL_REJECTION_REASONS.get(
            yakit, ('unsupported_fuel_key', None))[0]
        assert g.get('reason') == beklenen, g
        assert g.get('supported_fuels') == list(SUPPORTED_HYBRID_FUEL_KEYS), g

    def test_desteklenen_yakit_gecmeye_devam_ediyor(self, istemci):
        r = _hibrit(istemci, fuel_type='htpb')
        assert r.status_code == 200


# =========================================================== OH-D17-10
class TestOHD1710GammaBandi:
    """γ fiziksel kabul bandı ADSIZ literal olarak yazılmaz."""

    def test_adsiz_band_kalmadi(self):
        agac = ast.parse(YANMA.read_text(encoding='utf-8'))
        adsiz = []
        for n in ast.walk(agac):
            if not isinstance(n, ast.Compare) or len(n.ops) != 2:
                continue
            sab = [c.value for c in [n.left] + list(n.comparators)
                   if isinstance(c, ast.Constant) and isinstance(c.value, float)]
            if 1.0 in sab and 2.0 in sab:
                adsiz.append(n.lineno)
        assert adsiz == [], (
            'γ bandı hâlâ adsız literal olarak yazılı, satır: %s' % adsiz)

    def test_tek_adlandirilmis_kaynak_calisiyor(self):
        from hrma.engines.combustion_analysis import (
            GAMMA_PHYSICAL_MAX, GAMMA_PHYSICAL_MIN, gamma_is_physical)
        assert GAMMA_PHYSICAL_MIN == 1.0 and GAMMA_PHYSICAL_MAX == 2.0
        assert gamma_is_physical(1.25) is True
        for kotu in (1.0, 2.0, 0.5, 2.5, float('nan'), float('inf'),
                     None, 'x'):
            assert gamma_is_physical(kotu) is False, kotu


# =============================================================== B4-13
def test_b4_13_hem_cikis_kalitesinde_olu_parametre_yok():
    f = _fonksiyon(ENJEKTOR, '_hem_exit_quality')
    assert f is not None
    parametreler = [a.arg for a in f.args.args]
    kullanilan = {n.id for n in ast.walk(f) if isinstance(n, ast.Name)}
    olu = [p for p in parametreler if p not in kullanilan]
    assert olu == [], 'ölü parametre geri gelmiş: %s' % olu
    assert 'p1_pa' not in parametreler


def test_b4_13_kalite_p1den_bagimsiz_KALMALI():
    """Çürütmenin sayısal kaydı: süper-şarj kaliteyi DEĞİŞTİRMEZ.

    Sıkıştırılamaz sıvının izotermal basınçlanması entropiyi değiştirmez,
    dolayısıyla x₂ = (s₁ − s_l)/s_fg yalnız (T₁, p₂)'ye bağlıdır.
    """
    from hrma.engines.injector_design import nhne_mass_flow, _SAT
    T1 = 290.0
    pv = _SAT.psat(T1) / 1e5
    a = nhne_mass_flow(0.66, 1e-5, pv + 5.0, 20.0, pv, T1)
    b = nhne_mass_flow(0.66, 1e-5, pv + 40.0, 20.0, pv, T1)
    assert a['quality_out'] == pytest.approx(b['quality_out'], rel=1e-12)
    # ...ama DEBİ p₁'i görmeli (yoksa bu bir kusur olurdu, çürütme değil).
    assert b['mdot_kg_s'] > a['mdot_kg_s']


# =============================================================== B4-14
def test_b4_14_bogulma_seciminde_olu_dal_yok():
    f = _fonksiyon(ENJEKTOR, 'hem_mass_flow')
    assert f is not None
    kosullu = [ast.unparse(n) for n in ast.walk(f) if isinstance(n, ast.IfExp)]
    assert kosullu == [], 'totolojik koşullu seçim geri gelmiş: %s' % kosullu


@pytest.mark.parametrize('T1', [270.0, 280.0, 290.0, 295.0])
@pytest.mark.parametrize('p2_bar', [1.0, 5.0, 10.0, 20.0, 30.0])
def test_b4_14_debi_akı_maksimumunun_ta_kendisi(T1, p2_bar):
    from hrma.engines.injector_design import (
        hem_mass_flow, hem_flux_solution, _SAT)
    p1 = _SAT.psat(T1) * 1.2
    p2 = p2_bar * 1e5
    if p2 >= p1:
        pytest.skip('p₂ ≥ p₁')
    hal = {'T1_K': T1, 'p1_pa': p1, 'p2_pa': p2}
    coz = hem_flux_solution(hal)
    assert hem_mass_flow(0.8, 1e-5, hal) == pytest.approx(
        0.8 * 1e-5 * coz['G'], rel=0.0, abs=0.0)
    # Boğulma teşhisi artık okunabilir ve akı maksimumuyla tutarlı.
    assert coz['choked'] == (coz['throat_pressure_pa'] > p2)


# =============================================================== B4-15
def test_b4_15_olu_akis_ozellikleri_yontemi_yok():
    from hrma.engines.nozzle_design import NozzleDesigner
    assert not hasattr(NozzleDesigner, 'calculate_nozzle_flow_properties')
    assert _fonksiyon(LULE, 'calculate_nozzle_flow_properties') is None


def test_b4_15_depoda_cagiran_kalmadi():
    c = subprocess.run(['git', 'grep', '-l',
                        'calculate_nozzle_flow_properties',
                        '--', 'hrma/', 'tools/'],
                       cwd=ROOT, capture_output=True, text=True)
    dosyalar = [s for s in c.stdout.splitlines()
                if s.strip() and not s.endswith('nozzle_design.py')]
    assert dosyalar == [], dosyalar


def test_b4_15_konik_yari_aci_tek_kaynak():
    """Kaldırılan gövdedeki 15.0 kopyası geri gelmesin."""
    from hrma.engines.nozzle_design import NozzleDesigner
    assert NozzleDesigner.CONICAL_HALF_ANGLE_DEG == 15.0
    assert NozzleDesigner.lambda_from_angle(15.0) == pytest.approx(
        0.5 * (1.0 + np.cos(np.radians(15.0))), rel=1e-15)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
