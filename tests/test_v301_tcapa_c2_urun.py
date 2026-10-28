"""V301/T-ÇAPA-C2 (27 Eki 2026) — kulvarın ÜRÜN düzeltmelerinin bekçileri.

Kanıt: ``docs/scofield/raw/OH/V301/tcapa-c2/RAPOR.md``.

1. BELGE D1/D2 — form ``min``/``max`` sunucu bandının KENDİSİDİR (tek kaynak):
   katı ``ambient_temp`` (``solid_rocket_engine._override_val``), sıvı
   viskozite ve oda cidar kalınlığı (``LIQUID_INPUT_BANDS``). Ölçülen kusur:
   form 180-340 K / 1e-6-0,1 Pa·s / 0,2-150 mm iken sunucu 200-350 K /
   1e-7-10 Pa·s / 0,2-500 mm kabul ediyordu (form 190 K'ye izin veriyor,
   sunucu 422 veriyordu; 200 mm cidarı form reddediyordu).
2. BELGE D3 — hibrit plaka kalınlığı boşken modül 3,0 mm VARSAYILANLA L/D
   (ölçüldü 1,5547) ve ``plate_thickness`` 3,0 yayımlıyor
   (``plate_thickness_earned = false``). Tasarım raporu ve dışa aktarım bu
   iki sayıyı YALNIZ kazanılmışsa basar/taşır.
3. KABUL U3 — dil değişimi enjektör alanlarını boşaltmaz (tarayıcı bekçisi
   ``tests/test_v301_kabul_ui.py::test_u3_…``); burada kaynak sözleşmesi.
"""
import pathlib
import re
import shutil
import subprocess
import json

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
SOLID = KOK / 'hrma' / 'templates' / 'solid.html'
LIQUID = KOK / 'hrma' / 'templates' / 'liquid.html'
ADV = KOK / 'hrma' / 'templates' / 'advanced.html'
APP_JS = KOK / 'hrma' / 'static' / 'js' / 'app.js'
NODE = shutil.which('node')


def _oku(yol):
    return yol.read_text(encoding='utf-8')


def _girdi_bandi(html, alan):
    etiketler = re.findall(r'<input\b[^>]*\bid="%s"[^>]*>' % re.escape(alan), html)
    assert len(etiketler) >= 1, f'{alan} girdisi yok'
    bantlar = set()
    for e in etiketler:
        lo = re.search(r'\bmin="([^"]+)"', e)
        hi = re.search(r'\bmax="([^"]+)"', e)
        assert lo and hi, f'{alan}: tarayıcı kapısı (min/max) yok'
        bantlar.add((float(lo.group(1)), float(hi.group(1))))
    assert len(bantlar) == 1, f'{alan}: aynı kimlikte farklı bantlar {bantlar}'
    return bantlar.pop()


def test_d1_kati_ortam_sicakligi_form_bandi_sunucu_bandi():
    motor = _oku(KOK / 'hrma' / 'engines' / 'solid_rocket_engine.py')
    m = re.search(r"_override_val\('ambient_temp',\s*([-\d.eE]+),\s*([-\d.eE]+)\)",
                  motor)
    assert m, 'sunucunun ambient_temp bandı bulunamadı'
    sunucu = (float(m.group(1)), float(m.group(2)))
    assert _girdi_bandi(_oku(SOLID), 'ambient_temp') == sunucu


@pytest.mark.parametrize('alan', ['fuel_viscosity', 'oxidizer_viscosity',
                                  'chamber_wall_thickness'])
def test_d2_sivi_form_bandi_sunucu_bandi(alan):
    from hrma.engines.liquid_rocket_engine import LIQUID_INPUT_BANDS
    lo, hi = LIQUID_INPUT_BANDS[alan][:2]
    assert _girdi_bandi(_oku(LIQUID), alan) == (lo, hi)


def test_d2_viskozite_ipucu_kabul_araligini_iki_dilde_soyler():
    from hrma.engines.liquid_rocket_engine import LIQUID_INPUT_BANDS
    lo, hi = LIQUID_INPUT_BANDS['fuel_viscosity'][:2]
    assert (lo, hi) == LIQUID_INPUT_BANDS['oxidizer_viscosity'][:2]
    sozluk = _oku(KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js')
    for anahtar in ('liq.ui.fuel_dynamic_viscosity_at_operating_temperature',
                    'liq.ui.oxidizer_dynamic_viscosity_at_operating_temperat'):
        degerler = re.findall(r"'%s':\s*'([^']*)'" % re.escape(anahtar), sozluk)
        assert len(degerler) == 2, anahtar
        en, tr = degerler
        lo_s = ('%g' % lo).replace('e-0', 'e-')      # 1e-07 -> 1e-7
        assert 'Accepted range: %s to %g Pa·s' % (lo_s, hi) in en, en
        assert 'Kabul aralığı: %s ile %g Pa·s arası' % (lo_s, hi) in tr, tr


def test_d3_kazanilmamis_plakanin_varsayilan_sayilari_disa_aktarilmaz():
    src = _oku(APP_JS)
    i = src.index("...(results.injector.type === 'showerhead' && {")
    govde = src[i:src.index('}),', i)]
    assert "plate_thickness_earned === true" in govde
    assert re.search(r"l_over_d_ratio:\s*\(results\.injector\.plate_thickness_earned"
                     r" === true\)", govde), govde
    assert re.search(r"plate_thickness_mm:\s*\(results\.injector\.plate_thickness_earned"
                     r" === true\)", govde), govde


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_d3_rapor_ld_satiri_kazanilmamissa_sayi_basmaz(tmp_path):
    """Rapor satırı kuralı node'da: kazanılmamış L/D sayısı ekrana çıkmaz."""
    src = _oku(APP_JS)
    i = src.index("injectorRows.push([T('app.rep.ldRatio'")
    son = src.index(']);', i) + 3
    satir = src[i:son]
    betik = tmp_path / 'ld.js'
    betik.write_text(
        "const T = (k, d) => k + '|' + d;\n"
        "const numTxt = (v, d) => v.toFixed(d);\n"
        "function kos(injectorData) { const injectorRows = [];\n"
        + satir + "\n return injectorRows[0][1]; }\n"
        "process.stdout.write(JSON.stringify({\n"
        "  kazanilmis: kos({l_d_ratio: 3.9, l_d_ratio_earned: true}),\n"
        "  kazanilmamis: kos({l_d_ratio: 1.5547, l_d_ratio_earned: false}),\n"
        "  yok: kos({})}));\n", encoding='utf-8')
    p = subprocess.run([NODE, str(betik)], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout)
    assert o['kazanilmis'] == '3.9'
    assert o['kazanilmamis'].startswith('app.rep.ldNotEarned|'), o
    assert '1.5' not in o['kazanilmamis']
    assert o['yok'] == 'N/A'


def test_u3_dil_yeniden_basimi_degerleri_korur_kaynak_sozlesmesi():
    adv = _oku(ADV)
    i = adv.index('function updateInjectorParams()')
    govde = adv[i:adv.index('\n        }\n', adv.index('paramsDiv.innerHTML = html;', i))]
    assert "arguments[0] === true" in govde
    assert "getAttribute('data-inj-type') === type" in govde
    assert "setAttribute('data-inj-type', type)" in govde
    # İki dil işleyicisi de yeniden basımı "dil" diye işaretler.
    assert "updateInjectorParams(true)" in adv
    assert "updateInjectorParams(true)" in _oku(APP_JS)
    # Tip seçicisinin change olayı eski davranışta (bayat değer taşınmaz).
    assert 'onchange="updateInjectorParams()"' in adv


# ---------------------------------------------------------------------------
# BELGE §8.1-5 (S1) — Besleme / Çalkalanma sekmesi gizli sayısız doğar ve
# motorun KENDİ çalkalanma bloğundan tohumlanır.
# ÖLÇÜLDÜ (27 Eki, örnek hibrit): eski varsayılanlar 0,3 / 0,6 / 9,81 / 810 /
# 0,15 / 0,10 hiçbiri motordan değildi; tohumlanan değerlerle panelin
# /api/slosh-analysis f1'i motor bloğuyla BİT-AYNI (2,0701356788653476 Hz).
# ---------------------------------------------------------------------------
@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_s1_cakalanma_sekmesi_gizli_sayisiz_ve_motordan_tohumlanir(tmp_path):
    js = KOK / 'hrma' / 'static' / 'js'
    motor = {'oxidizer_tank_slosh': {
        'status': 'modelled', 'tank_diameter_m': 0.2134490081394525,
        'fill_height_m': 0.4535791422963364, 'g_eff_m_s2': 9.80665,
        'liquid_density_kg_m3': 785.1039703874175,
        'slosh': {'baffle': {'depth_ratio': 0.1}}}}
    betik = tmp_path / 'k.js'
    betik.write_text(
        "global.window = global; global.document = {getElementById(){return null;},"
        " addEventListener(){}}; global.T = (k, d) => d;\n"
        "require(%s); require(%s);\n" % (json.dumps(str(js / 'analysis_dock.js')),
                                         json.dumps(str(js / 'panels' / 'feed_panel.js')))
        + "const t = window.FeedPanel._tabs.filter(x => x.key === 'slosh')[0];\n"
        "process.stdout.write(JSON.stringify({def: t.fields.map(f => [f[0], f[2]]),"
        " sug: t.suggest(%s), bos: t.suggest({})}));\n" % json.dumps(motor),
        encoding='utf-8')
    p = subprocess.run([NODE, str(betik)], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout)
    sayili = [k for k, v in o['def'] if v != '']
    assert not sayili, f'çalkalanma alanları gizli sayıyla doğuyor: {sayili}'
    s = o['sug']
    assert s['radius'] == pytest.approx(0.2134490081394525 / 2, rel=0, abs=0)
    assert s['fill_height'] == 0.4535791422963364
    assert s['g_eff'] == 9.80665
    assert s['fluid_density'] == 785.1039703874175
    assert s['baffle_depth_ratio'] == 0.1
    assert 'baffle_width_ratio' not in s
    assert o['bos'] == {}, 'motor bloğu yokken sayı uyduruluyor'


# ---------------------------------------------------------------------------
# BELGE §8.1-2 — hibrit Performans Özeti kartı: künye dar sütuna harf harf
# kırılıyordu (başlığın esnek satırında etiketle yan yana) ve ham
# 'NOT_EVALUATED' kodu basılıyordu. ÖLÇÜLDÜ (kanıt kart_olcum.json): künye
# genişliği kartın tamamı (1280: 196/230 px, 1440: 228/262 px), çakışma 0,
# taşan kart 0, ham kod 0 (EN/TR × 1280/1440).
# ---------------------------------------------------------------------------
def test_kart_kunyesi_baslik_satirinin_disinda():
    src = _oku(APP_JS)
    i = src.index('<div class="hd-metric-head">')
    bas = src[i:src.index('<div class="hd-metric-value">', i)]
    kapanis = bas.index('</div>\n                </div>')
    assert '${note}' not in bas[:kapanis], (
        'künye yine başlığın esnek satırında (dar sütun)')
    assert '${note}' in bas[kapanis:]


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_ham_not_evaluated_kodu_ekrana_basilmaz(tmp_path):
    src = _oku(APP_JS)
    i = src.index('function HUKUM_SOZCUGU(kod)')
    govde = src[i:src.index('\n}\n', i) + 2]
    betik = tmp_path / 'h.js'
    betik.write_text(
        "const T = (k, d) => 'T:' + k;\nconst SRV = s => 'SRV:' + s;\n" + govde
        + "\nprocess.stdout.write(JSON.stringify([HUKUM_SOZCUGU('NOT_EVALUATED'),"
          " HUKUM_SOZCUGU('UNSAFE')]));\n", encoding='utf-8')
    p = subprocess.run([NODE, str(betik)], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == ['T:app.state.notEvaluated', 'SRV:UNSAFE']
    for kalip in ("attrSafe(SRV(m.stateWord))", "': ' + sf.status,",
                  "': ' + sf.risk_level,"):
        assert kalip not in src, f'ham hüküm kodu yolu geri geldi: {kalip}'


# ---------------------------------------------------------------------------
# BELGE §8.1-3 (kısmi) — TR ekranda kalan iki İngilizce/ham metin.
# ---------------------------------------------------------------------------
def test_besleme_bolum_ipucu_sozlukten():
    src = _oku(KOK / 'hrma' / 'static' / 'js' / 'panels' / 'feed_panel.js')
    assert "hint.textContent = 'slosh · pressurant · water-hammer'" not in src
    assert "T('panel.feed.sectionHint'" in src
    sozluk = _oku(KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js')
    degerler = re.findall(r"'panel\.feed\.sectionHint':\s*'([^']*)'", sozluk)
    assert degerler == ['slosh · pressurant · water hammer',
                        'çalkalanma · basınçlandırıcı · su koçu']


def test_yapisal_guverte_malzeme_rozeti_makine_anahtari_basmaz():
    src = _oku(KOK / 'hrma' / 'static' / 'js' / 'panels' / 'structural_panel.js')
    assert "String(dp.material).toUpperCase()" not in src, (
        "güverte rozeti yine 'MALZEME: STEEL' basıyor")
    i = src.index("T('common.material', 'MATERIAL')")
    assert 'matAd' in src[i:i + 120]


def test_hibrit_tasarim_tablosu_ingilizce_kalintilari_cevrilir():
    """BELGE §8.1-3: 'requested → achieved' ve 'injector circuit solution'."""
    src = _oku(APP_JS)
    assert "m requested &rarr;" not in src and "m achieved</strong>" not in src
    assert "T('app.rep.lStarRequested'" in src and "T('app.rep.lStarAchieved'" in src
    assert "SRV(injectorData.pressure_drop_source)" in src
    assert "SRV(String(injectorData.impingement_plan_source))" in src
    charts = _oku(KOK / 'hrma' / 'static' / 'js' / 'i18n_charts.js')
    assert re.findall(r"'injector circuit solution':\s*'([^']*)'", charts) == [
        'injector circuit solution', 'enjektör devresi çözümü']
    sozluk = _oku(KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js')
    assert re.findall(r"'app\.rep\.lStarRequested':\s*'([^']*)'", sozluk) == [
        'requested', 'istenen']
    assert re.findall(r"'app\.rep\.lStarAchieved':\s*'([^']*)'", sozluk) == [
        'achieved', 'gerçekleşen']


def test_belirsizlik_tutarlilik_notu_makine_adi_ve_ham_ingilizce_basmaz():
    """BELGE §8.1-3: 'consistency_note MC mean differs …' TR ekranda."""
    src = _oku(KOK / 'hrma' / 'static' / 'js' / 'panels' / 'uncertainty_panel.js')
    assert "+ 'consistency_note</span> ' + escapeHtml(note)" not in src
    i = src.index('data-uq-consistency-note')
    blok = src[src.rindex('if (note) {', 0, i):i + 200]
    assert "T('panel.uncertainty.consistencyNoteLabel'" in blok
    assert "I.serverText(note)" in blok
    assert "T('common.techDetailSrv'" in blok
