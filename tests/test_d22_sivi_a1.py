# -*- coding: utf-8 -*-
"""ÖH Dalga-22 · sıvı kulvarı aşama-1 bekçileri.

Her bekçi TERS-MUTASYONLA kanıtlanmıştır: onarım geçici olarak geri
alındığında ilgili test KIRMIZI olur (kanıt:
``docs/scofield/raw/OH/D22/sivi/a1/mutasyon.json``).

Kapsanan kalemler:
  * P6B4-02  — τ_c ↔ kalış süresi kalıntısının gerekçesi ÖLÇÜLMÜŞ ayrışma
  * P6B4-04  — kısma haritası çevrim hükmünü de taşır
  * P6B4-05  — chug atalet zinciri yanıtın KENDİ hattıyla çaprazlanır
  * P9B1-17  — baş kapak yapısal analizde boyutlandırılır
  * P17B2-10 — /liquid çip yığını: Isp referansı + O/F çipi
  * OH-D18-04 — daralma oranı kestiriminin künyesi doğrulanabilir kaynağa bağlı
  * OH-D19-14 — /calculate_liquid yanıtı openrocket bloğunu taşır
  * OH-D20-01 — Isp özdeşlik kapanış eşiği tek tanımlı + künyeli
  * OH-D20-05 — referans zinciri bandı türetilmiş (bkz. test_liquid_real_inputs)
"""
import contextlib
import io
import json
import os
import re

import pytest

from hrma.engines import liquid_rocket_engine as lre
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIQUID_PY = os.path.join(KOK, 'hrma', 'engines', 'liquid_rocket_engine.py')
LIQUID_HTML = os.path.join(KOK, 'hrma', 'templates', 'liquid.html')


def oku(yol):
    with open(yol, encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def sivi_sonuc():
    """Tek sıvı koşusu (pahalı): tüm alan bekçileri bunu paylaşır."""
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        motor = lre.LiquidRocketEngine(
            thrust=25000.0, chamber_pressure=60.0, mixture_ratio=2.2,
            fuel_type='rp1', oxidizer_type='lox',
            overrides={'expansion_ratio': 12.0, 'burn_time': 30.0})
        return motor, motor.calculate_performance()


def _derin_bul(d, ad, derinlik=0):
    if derinlik > 7 or not isinstance(d, dict):
        return None
    if ad in d:
        return d[ad]
    for v in d.values():
        if isinstance(v, dict):
            bulunan = _derin_bul(v, ad, derinlik + 1)
            if bulunan is not None:
                return bulunan
    return None


# ===========================================================================
# P6B4-02 — kalıntının gerekçesi ÖLÇÜM, tahmin değil
# ===========================================================================
def test_p6b402_kalinti_iki_adli_terime_TAM_ayrisir(sivi_sonuc):
    """Yayımlanan oran = (1/C_D)·(c*Γ)²/(R·T); artan sıfır olmalı."""
    _, sonuc = sivi_sonuc
    capraz = _derin_bul(sonuc, 'tau_c_vs_residence_time')
    assert capraz is not None, 'τ_c çaprazı yayımlanmıyor'
    ayrisma = capraz.get('residual_decomposition')
    assert ayrisma is not None, (
        'kalıntı ayrışması yayımlanmıyor: gerekçe yine ölçülmemiş bir '
        'iddiaya dönmüş (P6B4-02)')
    beklenen = (ayrisma['discharge_coefficient_term']
                * ayrisma['rt_identity_term'])
    assert beklenen == pytest.approx(capraz['ratio'], rel=1e-9)
    assert abs(ayrisma['unexplained_pct']) < 1e-6, ayrisma


def test_p6b402_debi_bogulmus_bogaz_ozdesliginden_GELIYOR(sivi_sonuc):
    """Eski gerekçenin çürütüldüğü ÖLÇÜM: ṁ = Pc·A_t·C_D/c* (birebir)."""
    motor, _ = sivi_sonuc
    mdot_bogaz = (float(motor.P_c) * 1e5 * float(motor.A_t)
                  / float(motor.c_star))
    assert float(motor.mdot_total) == pytest.approx(
        mdot_bogaz * float(motor.CD_throat), rel=1e-9), (
        'debi boğulmuş-boğaz özdeşliğinden gelmiyor; P6B4-02 ölçümü '
        'geçersizleşti, gerekçe metni yeniden ölçülmeli')


def test_p6b402_yanlis_gerekce_metni_GERI_DONMEDI():
    """Atıf yalanı nöbeti: 'debi boğazdan gelmez' iddiası geri gelmemeli."""
    assert 'not\n    from the choked-throat identity' not in \
        lre.LIQUID_TAU_C_RESIDUAL
    assert 'residual_decomposition' in lre.LIQUID_TAU_C_RESIDUAL, (
        'kalıntı gerekçesi okuyucuyu ölçülmüş ayrışmaya YÖNLENDİRMİYOR')


# ===========================================================================
# P6B4-04 — kısma haritası çevrim hükmünü taşır
# ===========================================================================
def test_p6b404_her_nokta_cevrim_hukmunu_TASIR(sivi_sonuc):
    _, sonuc = sivi_sonuc
    harita = sonuc['throttle_map']
    noktalar = harita.get('points') or []
    assert noktalar, 'kısma haritası boş'
    for n in noktalar:
        assert 'chug_loop_verdict' in n, (
            f"nokta çevrim hükmünü taşımıyor (P6B4-04): {n}")
        assert 'chug_loop_status' in n
    hukumlu = [n for n in noktalar if n.get('chug_loop_status') == 'modelled']
    assert hukumlu, 'hiçbir noktada çevrim çözülmemiş'
    for n in hukumlu:
        assert n['rule_vs_loop'] in ('agree', 'disagree')


def test_p6b404_cevrim_hukmu_KOPYA_DEGIL_yeniden_cozulmus(sivi_sonuc):
    """Her nokta kendi J'siyle çözülür: frekanslar birbirinin kopyası olamaz."""
    _, sonuc = sivi_sonuc
    noktalar = [n for n in sonuc['throttle_map'].get('points') or []
                if n.get('chug_loop_status') == 'modelled'
                and n.get('chug_loop_frequency_hz')]
    assert len(noktalar) >= 2
    frekanslar = {round(n['chug_loop_frequency_hz'], 9) for n in noktalar}
    assert len(frekanslar) == len(noktalar), (
        'noktalar aynı frekansı taşıyor — hüküm tasarım noktasından '
        'KOPYALANMIŞ olabilir (P6B4-04 sözleşmesi: her nokta kendi J\'siyle '
        'yeniden çözülür)')


def test_p6b404_celiski_sayilir_ve_YAYIMLANIR(sivi_sonuc):
    _, sonuc = sivi_sonuc
    beyan = sonuc['throttle_map'].get('chug_loop_across_throttle')
    assert isinstance(beyan, dict), 'çevrim beyanı yok'
    assert beyan.get('points_with_loop_verdict', 0) > 0
    assert 'points_where_rule_and_loop_disagree' in beyan
    assert 'tau_s' in beyan and 'tau_c_s' in beyan, (
        'dondurulan zaman ölçekleri beyan edilmiyor')


# ===========================================================================
# OH-D20-01 — Isp özdeşlik eşiği tek tanımlı + künyeli
# ===========================================================================
def test_ohd2001_esik_TEK_TANIMLI_ve_yayimlaniyor(sivi_sonuc):
    _, sonuc = sivi_sonuc
    kimlik = sonuc['isp_identity']
    assert kimlik['closure_tolerance_pct'] == pytest.approx(
        lre.LIQUID_ISP_IDENTITY_TOLERANCE_PCT)
    assert f'{lre.LIQUID_ISP_IDENTITY_TOLERANCE_PCT:g}%' in kimlik['basis'], (
        'künye eşiği sabitten TÜRETMİYOR — sabit değişirse metin yalan söyler')


def _kod_satirlari(kaynak):
    """Yorum satırlarını atar: künye METNİNDE eski literal geçebilir."""
    return [s for s in kaynak.splitlines() if not s.lstrip().startswith('#')]


def test_ohd2001_ciplak_literal_kodda_KALMADI():
    kod = '\n'.join(_kod_satirlari(oku(LIQUID_PY)))
    assert 'abs(_res) <= 0.5' not in kod, (
        'Isp özdeşlik eşiği yine çıplak literal (OH-D20-01)')
    # OH-D20-01'in ikinci ayağı (yedek dal kırpma bandı) D20'de kapanmıştı;
    # geri dönmediğini burada da kilitliyoruz.
    assert 'max(4, min(epsilon_optimal, 300))' not in kod
    assert lre.EXPANSION_RATIO_FALLBACK_MIN == 4.0
    assert lre.EXPANSION_RATIO_FALLBACK_MAX == 300.0


# ===========================================================================
# P17B2-10 — /liquid çip yığını
# ===========================================================================
def test_p17b210_isp_cipi_referansini_SOYLUYOR():
    kaynak = oku(LIQUID_HTML)
    assert "data.isp_reference = 'vacuum'" in kaynak, (
        'güverteye Isp referans beyanı gönderilmiyor: çip niteliksiz '
        'kalıyor (P17B2-10)')


def test_p17b210_of_cipi_DEGERIYLE_birlikte_besleniyor():
    kaynak = oku(LIQUID_HTML)
    assert 'data.of_ratio = ofOran' in kaynak, (
        'O/F çipi için `of_ratio` gönderilmiyor (P17B2-10)')
    # motor_viz3d.js O/F DEĞERİNİ yalnız of_ratio/of_ratio_initial'dan okur;
    # `mixture_ratio` tek başına gönderilirse çip doğar ama ekrana uydurma
    # `2.00` basılır. Sahte veri yasağı: alan adı of_ratio OLMAK ZORUNDA.
    assert 'data.mixture_ratio = ' not in kaynak, (
        'O/F yalnız `mixture_ratio` ile gönderilmiş: çip doğar ama değeri '
        'motor_viz3d.js\'in sabit 2 yedeğinden gelir (sahte veri)')


# ===========================================================================
# Kanıt dosyalarının varlığı (ölçüm olmadan onarım yok)
# ===========================================================================
def test_kanit_dosyalari_ONCE_SONRA_ciftleri_duruyor():
    kanit = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D22',
                         'sivi', 'a1')
    for ad in ('once_ham.json', 'sonra_ham.json', 'capa_once.json',
               'capa_sonra.json', 'mutasyon.json'):
        yol = os.path.join(kanit, ad)
        assert os.path.exists(kanit_gerekli(yol)), f'kanıt dosyası yok: {yol}'
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            json.load(f)


# ÖH D31 · OH-FT-04 (Fable TOPLU sivi-01) — KANIT HİJYENİ.
# Yukarıdaki bekçi beş dosyayı ADIYLA sınıyordu; dizindeki ALTINCI dosya
# (``once_p6b402.json``) listede olmadığı için hiç açılmamıştı ve ÖLÇÜLDÜ ki
# geçerli JSON DEĞİLDİ: başında 16 satır ``Effective C* set: ...`` stdout
# kirliliği vardı (json.loads "Expecting value: line 1 column 1"). Kanıt
# dosyası okunamıyorsa kanıt değildir. Dosya temizlendi (yalnız kirlilik
# silindi, JSON gövdesi bit-aynı) ve bekçi artık adı sabit listeden değil
# DİZİNDEN alıyor: yeni bir kanıt dosyası eklendiğinde otomatik kapsanır.
def test_kanit_dizinindeki_HER_json_gercekten_JSON():
    kanit = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D22',
                         'sivi', 'a1')
    adlar = sorted(a for a in os.listdir(kanit_gerekli(kanit)) if a.endswith('.json'))
    assert len(adlar) >= 6, (
        f'kanıt dizini beklenenden küçük ({adlar}) — dosya silinmiş olabilir')
    for ad in adlar:
        yol = os.path.join(kanit, ad)
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            ham = f.read()
        try:
            json.loads(ham)
        except ValueError as exc:
            raise AssertionError(
                f'{ad}: kanıt dosyası geçerli JSON değil ({exc}). Ölçüm '
                'çıktısına stdout karışmış olabilir; betiği 2>/dev/null ile '
                'değil, stdout ayrılmış hâlde koşun.') from None


# ===========================================================================
# Yardımcı: kaynak dosyada regex sayımı (mutasyon betiği için)
# ===========================================================================
def test_kaynak_desenleri_TEK_yerde():
    """Onarımların desenleri kopyalanmamış olmalı (tek kaynak)."""
    kaynak = oku(LIQUID_PY)
    assert kaynak.count('LIQUID_ISP_IDENTITY_TOLERANCE_PCT = ') == 1
    assert len(re.findall(r'^TAU_C_RESIDUAL_DECOMPOSITION_BASIS = ',
                          kaynak, re.M)) == 1
