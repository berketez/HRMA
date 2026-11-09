"""V306/SIVI-MODEL kalem 1-2 — kısma haritasında chug: oran kuralı ⟷ çevrim modeli.

Kalem 1 (M-SIVI-28, S1). ÖLÇÜLEN KUSUR (mühendis turu L1: 800 N LOX/RP-1,
Pc 15 bar, enjektör ΔP 3 bar → J = 0,2; ``docs/scofield/raw/OH/V306/
sivi-model/once.json``): kısma tablosu %100 noktasında "marj yeterli" (yalnız
ΔP/Pc oran kuralı), Analiz Merkezi aynı noktada aynı çevrim modeliyle
"KARARSIZ — besleme bağlaşımlı chug". Motor iki hükmü de yayımlıyordu
(``chug_loop_verdict``, ``rule_vs_loop``) ama tablo yalnız kuralı basıyordu;
PDF chug hükmünü hiç basmıyordu (``k1_pdf_once.json``). Onarım: iki kriter
yan yana adıyla, kuralın sağlanıp çevrimin kararlı demediği noktalar adıyla
(ekran + PDF).

Kalem 2 (FİZİK-2 AÇIK). Pintle'da tasarım noktası hükmü iki atomizasyon
ölçeğiyle veriliyor, kısma haritası ise yalnız nominal ölçekle koşuyordu
(FİZİK-2 ölçüm koşulunda %100 noktası ``unstable`` ⟷ tasarım noktası
``marginal``). Harita artık her noktada aynı denetimi koşar.
"""
import contextlib
import copy
import io
import json
import pathlib
import re

import pytest

from hrma.engines.liquid_rocket_engine import (
    CHUG_DP_PC_MIN_LIQUID, CHUG_DP_PC_RECOMMENDED_LIQUID,
    PINTLE_CHUG_NOMINAL_SCALE)
from tests.support import kabul
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
H = {'Host': '127.0.0.1:8080'}
# Mühendis turu L1 vakası docs/ kanıtıdır: docs'suz yayın dalında yalnız onu
# okuyan testler kanıt kapısından atlanır (ÖH D36 kanit-atlama; içe aktarma
# anında okumak bütün dosyayı düşürüyordu).
L1_YOL = (KOK / 'docs/scofield/raw/OH/V306/muhendis-turu/sivi/vakalar/'
          'L1.json')
HTML = (KOK / 'hrma/templates/liquid.html').read_text(encoding='utf-8')
I18N = (KOK / 'hrma/static/js/i18n_pages.js').read_text(encoding='utf-8')


def _sessiz(fn, *a, **k):
    t = io.StringIO()
    with contextlib.redirect_stdout(t), contextlib.redirect_stderr(t):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _sivi(client, govde):
    r = _sessiz(client.post, '/calculate_liquid', json=govde, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def l1(client):
    vaka = json.loads(kanit_gerekli(L1_YOL).read_text(encoding='utf-8'))
    return _sivi(client, copy.deepcopy(vaka['istekler'][0]['govde']))


@pytest.fixture(scope='module')
def pintle_duyarli(client):
    """FİZİK-2 ölçüm koşulu (Pc 70, O/F 2,3): iki ölçeğin hükmü ayrışır."""
    return _sivi(client, dict(kabul.sayfa_yuku('liquid'),
                              injector_type='pintle', chamber_pressure=70,
                              mixture_ratio=2.3))


def _nokta(s, f):
    return next(p for p in s['throttle_map']['points']
                if abs(p['throttle_fraction'] - f) < 1e-9)


# ---------------------------------------------------------------------------
# Kalem 1 — motor yanıtı
# ---------------------------------------------------------------------------
def test_l1_tasarim_noktasi_kural_saglaniyor_cevrim_kararsiz(l1):
    p = _nokta(l1, 1.0)
    assert p['injector_dp_over_pc'] == pytest.approx(0.2, rel=1e-12)
    assert p['chug_rating'] == 'chug_margin_ok'
    assert p['chug_loop_verdict'] == 'unstable'
    # Tasarım noktasının çevrimi (Analiz Merkezi'nin koştuğu model) aynı hüküm.
    dongu = l1['combustion_analysis']['stability_analysis']['chug_loop']
    assert dongu['verdict'] == 'unstable'
    assert dongu['rule_vs_loop']['agreement'] == 'disagree'


def test_l1_kural_evet_cevrim_hayir_noktalari_adiyla(l1):
    tl = l1['throttle_map']['chug_loop_across_throttle']
    beklenen = [p['throttle_fraction'] for p in l1['throttle_map']['points']
                if p['chug_rating'] in ('chug_margin_ok',
                                        'chug_margin_marginal')
                and p['chug_loop_verdict'] != 'stable']
    assert beklenen == [0.85, 1.0]
    assert tl['rule_safe_but_loop_not_stable_fractions'] == beklenen


def test_oran_kurali_esikleri_yanitta(l1):
    rr = l1['throttle_map']['ratio_rule']
    assert rr['recommended_dp_over_pc'] == CHUG_DP_PC_RECOMMENDED_LIQUID
    assert rr['minimum_dp_over_pc'] == CHUG_DP_PC_MIN_LIQUID


# ---------------------------------------------------------------------------
# Kalem 1 — ekran (liquid.html) ve sözlük
# ---------------------------------------------------------------------------
def _blok():
    i = HTML.index('// 3) Kısma haritası')
    return HTML[i:HTML.index('// 4) Autogenous', i)]


def test_tablo_iki_kriteri_yan_yana_basar():
    b = _blok()
    assert "T('liq.cyc.col_loop'" in b and 'data-chug-loop=' in b
    assert "TF('liq.cyc.col_rule'" in b
    assert 'rule_safe_but_loop_not_stable_fractions' in b
    assert "TF('liq.cyc.rule_loop_disagree'" in b
    # Çevrim hükmü Analiz Merkezi'nin hüküm sözcükleriyle (tek sözlük).
    for v in ('stable', 'marginal', 'unstable'):
        assert "T('liq.cyc.loop_%s'" % v in b
    # Eski tek sütun ("Chug marjı") yok.
    assert "T('liq.cyc.chug'," not in b


def test_cevrim_kararli_demedigi_noktada_kural_yesil_boyanmaz():
    b = _blok()
    assert "var celiski = p.rule_vs_loop === 'disagree';" in b
    m = re.search(r"var chugCol = celiski \? 'var\(--hd-ink-dim", b)
    assert m, 'çelişkili noktada kural hücresi nötr renkte olmalı'


KISMA_I18N_ANAHTARLARI = ('liq.cyc.loop_stable', 'liq.cyc.loop_marginal',
                          'liq.cyc.loop_unstable', 'liq.cyc.col_dp_pc', 'liq.cyc.col_rule', 'liq.cyc.col_rule_plain',
              'liq.cyc.col_loop', 'liq.cyc.loop_marginal_scale',
              'liq.cyc.loop_not_evaluated', 'liq.cyc.rule_loop_disagree',
              'liq.cyc.scale_sensitive', 'liq.cyc.scale_rejected',
              'liq.cyc.throttle_rule_note')


@pytest.mark.parametrize("anahtar", KISMA_I18N_ANAHTARLARI)
def test_yeni_anahtarlar_iki_dilde(anahtar):
    assert I18N.count("'%s':" % anahtar) == 2, anahtar


def test_marj_yeterli_ifadesi_kalkti():
    assert "'marj yeterli'" not in I18N
    assert "'margin OK'" not in I18N
    assert "'liq.cyc.chug_state_ok': 'kural sağlanıyor'" in I18N


# ---------------------------------------------------------------------------
# Kalem 1 — PDF
# ---------------------------------------------------------------------------
def test_pdf_cevrim_ve_kural_hukmunu_birlikte_basar(l1):
    from hrma.export.pdf_generator import PDFReportGenerator
    satir = PDFReportGenerator._chug_verdict_line(l1, {})
    assert satir is not None
    assert 'chug loop model UNSTABLE' in satir
    assert 'classical ratio rule met at dP_inj/Pc = 0.2' in satir
    assert 'The two disagree' in satir
    assert 'not say stable at 85 %, 100 %' in satir
    assert 'chug_margin_ok' not in satir      # ham enum basılmaz


def test_pdf_cevrim_blogu_yoksa_satir_yok():
    from hrma.export.pdf_generator import PDFReportGenerator
    assert PDFReportGenerator._chug_verdict_line({}, {}) is None


# ---------------------------------------------------------------------------
# Kalem 2 — pintle iki ölçek her kısma noktasında
# ---------------------------------------------------------------------------
def test_pintle_her_noktada_iki_olcek(pintle_duyarli):
    tl = pintle_duyarli['throttle_map']['chug_loop_across_throttle']
    assert tl['atomisation_scale_check_applied'] is True
    for p in pintle_duyarli['throttle_map']['points']:
        chk = p['atomisation_scale_check']
        assert chk['status'] == 'modelled'
        assert set(chk['scales']) == {'annulus_gap_t', 'radial_hole_d'}
        if chk['verdicts_agree']:
            assert p['chug_loop_verdict'] == chk['scales'][
                PINTLE_CHUG_NOMINAL_SCALE]['verdict']
        else:
            assert p['chug_loop_verdict'] == 'marginal'
            assert p['chug_loop_nominal_verdict'] == chk['scales'][
                PINTLE_CHUG_NOMINAL_SCALE]['verdict']


def test_pintle_tasarim_noktasi_ile_yuzde_yuz_ayni_hukum(pintle_duyarli):
    dongu = pintle_duyarli['combustion_analysis']['stability_analysis'][
        'chug_loop']
    assert dongu['verdict'] == 'marginal'
    p = _nokta(pintle_duyarli, 1.0)
    assert p['chug_loop_verdict'] == dongu['verdict']
    tl = pintle_duyarli['throttle_map']['chug_loop_across_throttle']
    assert 1.0 in tl['atomisation_scale_sensitive_fractions']
    # Duyarlı olmayan noktalar listede yok (adıyla, eksiksiz).
    duyarli = [p['throttle_fraction']
               for p in pintle_duyarli['throttle_map']['points']
               if p['atomisation_scale_check']['verdicts_agree'] is False]
    assert tl['atomisation_scale_sensitive_fractions'] == duyarli


def test_pintle_disi_noktada_olcek_kaydi_yok(l1):
    for p in l1['throttle_map']['points']:
        assert 'atomisation_scale_check' not in p


def test_pdf_satiri_rapor_niteleyicilerinde(l1):
    """Satır PDF'in sonuç niteleyici listesine bağlı (çağrı yeri)."""
    from hrma.export.pdf_generator import PDFReportGenerator
    satirlar = PDFReportGenerator._result_qualifier_lines(l1, {})
    assert any('Chug (design point)' in s for s in satirlar)
