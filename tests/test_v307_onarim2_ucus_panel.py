"""V307/ONARIM2-UÇUŞ-PANEL — 6-DOF panelinin gösterim ve hüküm bekçileri
(mühendis turu 19 Kas, dalga 2; brif_20kas/ONARIM2_UCUS_PANEL.md).

Ne kilitlenir (sözleşme ve gösterim kuralı; bugünkü çıktı değil):
  * M7-UCUS-4 (a): ORTAK istemci kuralı — iki neden kodu
    (``BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI`` ⟷ ``BAGLASIK_KOSU_KARARSIZ_PENCERE``)
    ayrı adlarla; sınır ``t_gecersiz_bas_s``, null ise FAIL-CLOSED; yayımlanan
    apoje rijit koşudan ve "çalkantısız referans koşu" etiketiyle.
  * M7-UCUS-17: bağlaşık koşu grafiklerde geçerlilik sınırından sonra
    çizilmez (seri kesilir; sınır bilinmiyorsa hiç çizilmez).
  * M7-UCUS-14: apoje rozeti metre çözünürlüğünü de taşır.

Rozet bloğu GERÇEK dosyadan kesilip node'da koşturulur (test_faz5_ui
düzeneği; ``data`` burada tanımlıdır).
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
PANEL = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
I18N_C = (JS / 'i18n_common.js').read_text(encoding='utf-8')
NODE = shutil.which('node')

BADGE_BLOCK_START = 'const numOf = (v) =>'
BADGE_BLOCK_END = 'badges.innerHTML = html;'

#: Örnek hibrit (rüzgâr 5) koşusunun ölçülen yanıtından (ONARIM2-UÇUŞ-PANEL
#: kanıt dizini kosu/once/hib_ornek/api.json): pencere 3,535 s'de başlıyor,
#: bağlaşık tüm-uçuş alanları null, rijit referans apoje 5153,9 m @ 30,4 s.
OZET_PENCERE = {
    'apogee': None, 'apogee_time': None, 'stable': None, 'max_mach': None,
    'max_speed': None, 'max_alpha_deg': None, 'apogee_datum': 'above_launch_site',
    'static_margin_full': 2.0106, 'static_margin_empty': 1.4979,
    'cn_alpha': 14.60, 'x_cp': 1.54868, 'end_reason': 'apogee',
    'flight_verdict': {'flight': 'apogee', 'stability': 'stability_not_evaluated'},
}
RIJIT = {'apogee': 5153.9, 'apogee_time': 30.4, 'max_alpha_deg': 3.29}


def _sozluk(anahtar, dil):
    bulunan = re.findall(r"^\s*'%s': '((?:[^'\\]|\\.)*)',$" % re.escape(anahtar),
                         I18N_C, re.M)
    assert len(bulunan) == 2, (anahtar, len(bulunan))
    return bulunan[{'en': 0, 'tr': 1}[dil]].replace("\\'", "'")


def _js_islevi(kaynak, ad):
    bas = kaynak.index('function ' + ad + '(')
    i = kaynak.index('{', bas)
    derinlik = 0
    for j in range(i, len(kaynak)):
        if kaynak[j] == '{':
            derinlik += 1
        elif kaynak[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[bas:j + 1]
    raise AssertionError(ad + ' kapanmıyor')


def _rozet(tmp_path, ozet, veri, ad):
    bas = PANEL.index(BADGE_BLOCK_START)
    blok = PANEL[bas:PANEL.index(BADGE_BLOCK_END, bas)]
    betik = tmp_path / ('rozet_%s.js' % ad)
    betik.write_text(
        "'use strict';\n"
        "const s = " + json.dumps(ozet) + ";\n"
        "const data = " + json.dumps(veri) + ";\n"
        "const usedCurve = true;\nconst sayfaMotoru = null;\nconst aracKuru = null;\n"
        "function badge(text, kind) { return '[' + kind + ']' + text + '\\n'; }\n"
        "function T(k, f) { return f; }\n"
        "function TF(k, p, f) {\n"
        "  return String(f).replace(/\\{(\\w+)\\}/g,"
        " (w, n) => (p && n in p) ? String(p[n]) : w);\n"
        "}\n" + blok + "\nprocess.stdout.write(html);\n", encoding='utf-8')
    p = subprocess.run([NODE, str(betik)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout


def _yayim(neden, t):
    return {'calkanti': {'yayim': {'neden_kodu': neden, 't_gecersiz_bas_s': t,
                                   't_ilk_asim_s': t if neden and 'SINIRI' in neden else None},
                         'rijit_karsilastirma': RIJIT}}


# ===========================================================================
# 1. M7-UCUS-4 (a) — rozet iki nedeni adıyla söyler
# ===========================================================================
@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
class TestRozetIkiNeden:

    def test_pencere_kodu_degerlendirilmedi_rozetine_dusmez(self, tmp_path):
        """ÖNCE (ölçüldü, örnek hibrit TR 1440): yeni kodla rozet
        "KARARLILIK DEĞERLENDİRİLMEDİ" (stable = null) ve apoje rozeti yok.
        SONRA: nedeni adıyla söyleyen rozet + rijit referans apoje etiketiyle."""
        out = _rozet(tmp_path, OZET_PENCERE,
                     _yayim('BAGLASIK_KOSU_KARARSIZ_PENCERE', 3.535), 'pencere')
        assert 'STABILITY NOT EVALUATED' not in out, out
        assert '[err]SLOSH-INDUCED INSTABILITY WINDOW IN THE BURN (from t = 3.54 s)' in out, out
        assert 'depends on the initial disturbance' in out
        assert '[warn]SLOSH-FREE REFERENCE RUN — APOGEE 5.15 km (5153.9 m) @ 30.4 s AGL' in out, out
        # bağlaşık apoje / "zirve bulunamadı" uydurulmaz
        assert 'APOGEE NOT REPORTED' not in out and 'null' not in out and 'NaN' not in out

    def test_sinir_asimi_sinirini_t_gecersiz_bas_s_den_alir(self, tmp_path):
        out = _rozet(tmp_path, dict(OZET_PENCERE),
                     _yayim('BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI', 27.9277), 'asim')
        assert 'LINEAR VALIDITY LIMIT AT t = 27.93 s' in out, out
        assert 'SLOSH-INDUCED' not in out
        assert 'SLOSH-FREE REFERENCE RUN' in out

    def test_sinir_bilinmiyorsa_fail_closed_ve_tire_yok(self, tmp_path):
        for neden, parca in (('BAGLASIK_KOSU_KARARSIZ_PENCERE', 'instability window'),
                             ('BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI', 'passed the linear validity limit')):
            out = _rozet(tmp_path, OZET_PENCERE, _yayim(neden, None), 'null')
            assert '[err]COUPLED RUN OUTSIDE VALIDITY — ' in out, out
            assert parca in out and 'whole coupled run' in out
            assert 't = —' not in out and 'STABILITY NOT EVALUATED' not in out

    def test_neden_yoksa_rijit_rozeti_yok(self, tmp_path):
        ozet = dict(OZET_PENCERE, apogee=3207.5647, apogee_time=21.29, stable=True)
        out = _rozet(tmp_path, ozet, _yayim(None, None), 'gecerli')
        assert 'SLOSH-FREE REFERENCE RUN' not in out and 'COUPLED' not in out
        # M7-UCUS-14: metre çözünürlüğü aynı rozette (sürüm notu 3 207,6 m)
        assert '[info]APOGEE 3.21 km (3207.6 m) @ 21.3 s AGL' in out, out

    def test_rijit_apoje_yoksa_sayi_uydurulmaz(self, tmp_path):
        veri = _yayim('BAGLASIK_KOSU_KARARSIZ_PENCERE', 3.535)
        veri['calkanti']['rijit_karsilastirma'] = {'apogee': None, 'apogee_time': None}
        out = _rozet(tmp_path, OZET_PENCERE, veri, 'rijit_yok')
        assert 'SLOSH-FREE REFERENCE RUN' not in out


# ===========================================================================
# 2. M7-UCUS-17 — bağlaşık seri geçerlilik sınırında kesilir
# ===========================================================================
@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_bagli_seri_sinirda_kesilir_sinir_yoksa_bos():
    betik = (_js_islevi(PANEL, 'bagliGecerliSeri')
             + "\nconst ser = {time: [0, 1, 2, 3, 4], altitude: [0, 10, 20, 30, 40],"
               " mach: [0, .1, .2, .3, .4], kisa: [7]};\n"
               "const v = (n, t) => ({calkanti: {yayim: {neden_kodu: n, t_gecersiz_bas_s: t}}});\n"
               "console.log(JSON.stringify(["
               "bagliGecerliSeri(ser, v('BAGLASIK_KOSU_KARARSIZ_PENCERE', 2.0)),"
               "bagliGecerliSeri(ser, v('BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI', 2.5)),"
               "bagliGecerliSeri(ser, v('BAGLASIK_KOSU_KARARSIZ_PENCERE', null)),"
               "bagliGecerliSeri(ser, v(null, null)),"
               "bagliGecerliSeri(ser, {summary: {}})]));")
    p = subprocess.run([NODE], input=betik, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    pen, asim, bos, yok, kayit_yok = json.loads(p.stdout)
    assert pen['kesildi'] and pen['ser']['time'] == [0, 1, 2]
    assert pen['ser']['altitude'] == [0, 10, 20] and pen['ser']['kisa'] == [7]
    assert asim['ser']['time'] == [0, 1, 2] and asim['ser']['mach'] == [0, .1, .2]
    assert bos['kesildi'] and bos['ser']['time'] == [] and bos['ser']['altitude'] == []
    assert not yok['kesildi'] and yok['ser']['time'] == [0, 1, 2, 3, 4]
    assert not kayit_yok['kesildi']


def test_grafikler_kesilmis_seriyi_cizer():
    govde = PANEL[PANEL.index("const cizim = bagliGecerliSeri(ser, data);"):]
    govde = govde[:govde.index('// T12 (2026-08-03)')]
    for parca in ("x: serC.time, y: serC.altitude", "x: serC.time, y: serC.mach",
                  "drawAlphaPlot(alphaDiv, serC,", "x: serC.east, y: serC.north, mode: 'lines+markers'",
                  "x: serC.east, y: serC.north, z: serC.altitude"):
        assert parca in govde, parca
    # kesilen seride "Apoje" işaretçisi yok (en yüksek örnek apoje değildir)
    assert "(!cizim.kesildi && numOf(s.apogee) !== null) ? [" in govde
    assert re.search(r"x: ser\.(time|east)", govde) is None


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_irtifa_basligi_iki_nedeni_ayirir():
    betik = ("function T(k, f) { return f; }\n"
             "function TF(k, p, f) { return f.replace('{t}', p.t); }\n"
             "function sayiEkran(v, n) { return v.toFixed(n); }\n"
             + _js_islevi(PANEL, 'bagliGecersizBaslik')
             + "\nconst v = (n, t) => ({calkanti: {yayim: {neden_kodu: n, t_gecersiz_bas_s: t}}});\n"
               "console.log(JSON.stringify([bagliGecersizBaslik(v('BAGLASIK_KOSU_KARARSIZ_PENCERE', 3.535)),"
               " bagliGecersizBaslik(v('BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI', 27.9277)),"
               " bagliGecersizBaslik(v('BAGLASIK_KOSU_KARARSIZ_PENCERE', null)),"
               " bagliGecersizBaslik(v(null, null))]));")
    p = subprocess.run([NODE], input=betik, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    pen, asim, bos, yok = json.loads(p.stdout)
    assert 'instability window from t = 3.54 s' in pen and 'drawn only up to' in pen
    assert 'not valid after t = 27.93 s' in asim
    assert 'validity limit not known' in bos and 'not drawn' in bos
    assert yok is None


def test_yeni_anahtarlar_iki_dilde():
    for anahtar, tr_parca, en_parca in (
            ('sixdof.coupledWindow', 'KARARSIZLIK PENCERESİ', 'INSTABILITY WINDOW'),
            ('sixdof.coupledWholeInvalid', 'GEÇERLİLİK DIŞINDA', 'OUTSIDE VALIDITY'),
            ('sixdof.coupledReasonWindow', 'kararsızlık penceresi', 'instability window'),
            ('sixdof.coupledReasonLimit', 'doğrusal geçerlilik sınırını', 'linear validity limit'),
            ('sixdof.chartAltCoupledWindow', 'yalnız o ana kadar', 'only up to'),
            ('sixdof.chartAltCoupledNoLimit', 'çizilmedi', 'not drawn'),
            ('sixdof.badgeRigidRefApogee', 'ÇALKANTISIZ REFERANS KOŞU', 'SLOSH-FREE REFERENCE RUN'),
            ('sixdof.badgeApogee', '({m} m)', '({m} m)')):
        assert tr_parca in _sozluk(anahtar, 'tr'), anahtar
        assert en_parca in _sozluk(anahtar, 'en'), anahtar
    assert '{t}' in _sozluk('sixdof.coupledWindow', 'tr')
    assert '{neden}' in _sozluk('sixdof.coupledWholeInvalid', 'tr')
    assert '{datum}' in _sozluk('sixdof.badgeRigidRefApogee', 'tr')


# ===========================================================================
# 3. M7-UCUS-3 — şema koşudan sonra sunucunun sayısını gösterir
# ===========================================================================
@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_sema_kosudan_sonra_sunucu_cp_kosudan_once_onizleme():
    """ÖNCE (ölçüldü, katı örnek): şema altı `◆ CP 0,928 m` (istemci
    önizlemesi) ⟷ rozet `CP 0,927 m` (sunucu x_cp 0,92722). SONRA: koşudan
    sonra şema sunucunun değerlerini taşır; eksik sunucu alanında önizleme."""
    betik = (_js_islevi(PANEL, 'semaDegerleri')
             + "\nconst bar = {xCp: 0.92801, cnAlpha: 26.52};\n"
               "const cg = {full: 0.779, empty: 0.779};\nconst g = {body_d: 0.091};\n"
               "const srv = {xCp: 0.92722, cnAlpha: 26.519, smFull: 1.6294, smEmpty: 1.6295,"
               " cgFull: 0.7790, cgEmpty: 0.7789};\n"
               "console.log(JSON.stringify([semaDegerleri(bar, cg, g, null),"
               " semaDegerleri(bar, cg, g, srv),"
               " semaDegerleri(bar, cg, g, Object.assign({}, srv, {xCp: null}))]));")
    p = subprocess.run([NODE], input=betik, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    onizleme, kosu, eksik = json.loads(p.stdout)
    assert onizleme['kosu'] is False and onizleme['xCp'] == 0.92801
    assert abs(onizleme['smFull'] - (0.92801 - 0.779) / 0.091) < 1e-12
    assert kosu['kosu'] is True and kosu['xCp'] == 0.92722
    assert kosu['smFull'] == 1.6294 and kosu['cgEmpty'] == 0.7789
    assert eksik['kosu'] is False and eksik['xCp'] == 0.92801


def test_sema_cp_etiketi_tek_kaynaktan_ve_kaynagini_soyler():
    govde = _js_islevi(PANEL, 'drawSchematic')
    assert "fmt(sd.xCp, 3) + ' m</span>'" in govde
    assert "fmt(bar.xCp" not in govde and 'X(bar.xCp)' not in govde
    assert "semaSunucu.anahtar === semaAnahtari(g)" in govde
    assert "'sixdof.schemaFromRun'" in govde and "'sixdof.schemaPreview'" in govde
    # render koşunun değerlerini şemaya verir
    assert 'semaSunucu = { anahtar: semaAnahtari(gSema), xCp: numOf(s.x_cp),' in PANEL
    for anahtar, tr, en in (('sixdof.schemaFromRun', '6-DOF koşusunun', '6-DOF run'),
                            ('sixdof.schemaPreview', 'önizleme', 'preview')):
        assert tr in _sozluk(anahtar, 'tr') and en in _sozluk(anahtar, 'en')


# ===========================================================================
# 4. M7-UCUS-6 — iki bant: marj < 0 KARARSIZ, 0 ≤ marj ≤ eşik SINIRDA
# ===========================================================================
@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_marj_bandi_negatif_kararsiz_sifir_bir_sinirda():
    """ÖNCE (ölçüldü, katı küçük kanat): `-4,00 / -4,00 cal — KARARSIZ /
    SINIRDA` (sm < 1 tek etiket)."""
    sabit = re.search(r"const STATIC_MARGIN_MIN_CAL = [0-9.]+;", PANEL).group(0)
    betik = ("const COLORS = {red: 'R', green: 'G', yellow: 'Y', orange: 'O'};\n"
             "function T(k, f) { return f; }\n"
             "function TF(k, p, f) { return String(f).replace('{lim}', p.lim); }\n"
             "function fmt(v, n) { return v.toFixed(n); }\n" + sabit + "\n"
             + _js_islevi(PANEL, 'marjAltBandi') + "\n" + _js_islevi(PANEL, 'marginBand')
             + "\n" + _js_islevi(PANEL, 'marginBandPair')
             + "\nconsole.log(JSON.stringify([[-4, -4], [-0.2, 1.5], [0, 2], [0.5, 1.2],"
               " [1.0, 1.6], [1.01, 1.6], [1.63, 1.63]].map(c => marginBandPair(c[0], c[1]).label)));")
    p = subprocess.run([NODE], input=betik, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    e = json.loads(p.stdout)
    assert e[0].startswith('UNSTABLE — centre of pressure ahead') and 'MARGINAL' not in e[0]
    assert e[1].startswith('UNSTABLE — centre of pressure ahead')
    assert e[2] == e[3] == e[4] == 'MARGINAL (0 to 1 calibre)'
    assert e[5] == e[6] == 'STABLE'


def test_marj_esigi_sunucu_sabitiyle_ayni():
    from hrma.analysis.six_dof_trajectory import STATIC_MARGIN_MIN_CAL
    js = float(re.search(r"const STATIC_MARGIN_MIN_CAL = ([0-9.]+);", PANEL).group(1))
    assert js == STATIC_MARGIN_MIN_CAL
    # bandın eski tek etiketi kullanılmıyor; eşik literali tek yerde
    assert "T('sixdof.bandUnstable'," not in PANEL
    assert 'alt <= 1.0' not in PANEL and 'sm < 1.0' not in PANEL
    assert 'KARARSIZ' in _sozluk('sixdof.bandUnstableNeg', 'tr')
    assert 'SINIRDA' in _sozluk('sixdof.bandMarginal', 'tr') and '{lim}' in _sozluk('sixdof.bandMarginal', 'tr')


# ===========================================================================
# 5. M7-UCUS-15 — şema marj etiketi HTML'de (≥ 12 px)
# ===========================================================================
def test_sema_marj_etiketi_svg_olcegine_bagli_degil():
    govde = _js_islevi(PANEL, 'drawSchematic')
    assert "'<text x=\"' + padX + '\" y=\"14\" font-size=\"12\"" not in govde
    assert "font-size:0.8rem; color:' + bd.color" in govde
    assert 'host.innerHTML = smEtiket +' in govde
    # MOTOR yazısı ekrandaki ölçekten ≥ 12 px
    assert 'const svgYazi = Math.max(10, 12 / olcek);' in govde
    # yazı gövdenin altında: eksendeki CG/CP işaretçileri üstüne binmez
    assert "(cy + R * k + svgYazi * 1.05)" in govde


# ===========================================================================
# 6. M7-UCUS-10 — ray çıkış hızı / anı ve itki-ağırlık çözümden, ekranda
# ===========================================================================
#: Katı örnek motorun sabit itki karşılığı (test_v307_onarim_ucus.KATI ile
#: aynı gövde; örnek proje alanları).
KATI = dict(body_diameter=0.091, body_length=1.06, nose_length=0.5,
            nose_type='ogive', fin_count=4, cd0=0.45, wind_speed=5,
            wind_direction_deg=0, launch_elevation_deg=90,
            launch_azimuth_deg=0, rail_length=5, dry_mass=3.42,
            propellant_mass=2.407, thrust=1298.5, burn_time=2.28)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def test_ray_cikisi_cozumden_ve_el_hesabiyla_uyumlu(client):
    """El hesabı (mühendis, `betik/elhesap.py`): v = √(2·a·L), a = F/m − g.
    Sabit itki 1298,5 N, m0 = 5,827 kg, L = 5 m → a ≈ 213,0 m/s², v ≈ 46,2 m/s,
    t ≈ 0,217 s (ray üstünde sürükleme ve kütle kaybı ihmal). Çözücünün
    değeri ilk ray-dışı örnektir (six_dof_slosh 'ray_cikisi' tanımı)."""
    import contextlib
    import io
    import math
    with contextlib.redirect_stdout(io.StringIO()):
        r = client.post('/api/six-dof-analysis', json=KATI)
    assert r.status_code == 200
    s = r.get_json()['summary']
    m0 = 3.42 + 2.407
    a = 1298.5 / m0 - 9.80665
    v_el, t_el = math.sqrt(2 * a * 5.0), math.sqrt(2 * 5.0 / a)
    assert abs(s['rail_exit_speed_m_s'] - v_el) / v_el < 0.03, (s['rail_exit_speed_m_s'], v_el)
    assert abs(s['rail_exit_time_s'] - t_el) / t_el < 0.03, (s['rail_exit_time_s'], t_el)
    assert 0.0 <= s['rail_exit_alpha_deg'] < 90.0
    # rüzgâr 5 m/s, v ≈ 46 m/s → bağıl rüzgâr açısı ≈ atan(5/46) ≈ 6,2°
    assert abs(s['rail_exit_alpha_deg'] - math.degrees(math.atan2(5.0, s['rail_exit_speed_m_s']))) < 1.0
    # T/W çözücünün kendi işlevinden (no-liftoff dalıyla aynı alan)
    assert s['thrust_to_weight_at_ignition'] == pytest.approx(1298.5 / (m0 * 9.80665), rel=2e-3)


def test_ray_cikisi_ornegi_tanimi():
    import numpy as np
    from hrma.analysis.six_dof_trajectory import rail_exit_sample
    t = np.array([0.0, 0.1, 0.2, 0.3])
    pos = np.array([[0, 0, 0, 0], [0, 0, 0, 0], [0.0, 1.0, 5.0, 9.0]])
    assert rail_exit_sample(t, pos, 5.0, 10.0) == 2
    assert rail_exit_sample(t, pos, 5.0, 0.15) is None   # yanma bitti
    assert rail_exit_sample(t, pos, 50.0, 10.0) is None  # ray aşılmadı


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_rozet_ray_cikisini_ve_hucum_acisi_nedenini_yazar(tmp_path):
    """ÖNCE (mühendis, hibrit 60 kg burun yükü): `STATİK MARJ 1,53 … —
    KARARLI` ve `KARARSIZ — … hücum açısı 29,2 derece`; ray çıkış hızı ve T/W
    hiçbir yerde yok. SONRA: ikisi rozette; hüküm nedeni adıyla."""
    ozet = {'apogee': 347.2, 'apogee_time': 9.5, 'stable': False,
            'max_alpha_deg': 30.32, 'static_margin_full': 1.5127,
            'static_margin_empty': 1.6928, 'end_reason': 'apogee',
            'rail_length_m': 5.0, 'rail_length_source': 'supplied',
            'rail_exit_time_s': 0.5769, 'rail_exit_speed_m_s': 18.385,
            'rail_exit_alpha_deg': 15.214, 'thrust_to_weight_at_ignition': 3.7231,
            'flight_verdict': {'flight': 'apogee', 'stability': 'alpha_above_linear_limit'}}
    out = _rozet(tmp_path, ozet, {'alpha_window': {'linear_limit_deg': 15}}, 'ray')
    assert '[info]RAIL EXIT 18.4 m/s @ t = 0.577 s' in out, out
    assert '[info]THRUST/WEIGHT AT IGNITION 3.72' in out, out
    assert ('the static margin is adequate (1.51 / 1.69 cal); the cause is the flight '
            'itself: the vehicle leaves the rail at 18.4 m/s (t = 0.577 s) and the relative '
            'wind there is at 15.2 deg') in out, out
    # bağlaşık koşu yayımlanmadıysa ray çıkışı yalnız sınırdan önceyse
    for t_sinir, var in ((10.23, True), (0.3, False), (None, False)):
        out = _rozet(tmp_path, dict(ozet, stable=None),
                     {'calkanti': {'yayim': {'neden_kodu': 'BAGLASIK_KOSU_KARARSIZ_PENCERE',
                                             't_gecersiz_bas_s': t_sinir}}}, 'ray_pen')
        assert ('RAIL EXIT' in out) is var, (t_sinir, out)


def test_ray_cikisi_anahtarlari_iki_dilde():
    for anahtar, tr in (('sixdof.badgeRailExit', 'RAY ÇIKIŞI'),
                        ('sixdof.badgeThrustWeight', 'İTKİ/AĞIRLIK'),
                        ('sixdof.verdictAlphaRailCause', 'statik marj yeterli'),
                        ('sixdof.verdictAlphaFlightCause', 'uçuşun kendisi')):
        assert tr in _sozluk(anahtar, 'tr'), anahtar
        assert _sozluk(anahtar, 'en') != _sozluk(anahtar, 'tr')


# ===========================================================================
# 7. M7-UCUS-15 — N₂O ve α simgesi
# ===========================================================================
def test_n2o_alt_simgeli_ve_alfa_simgesi():
    """ÖNCE (ölçüldü): 'İTKİ: MOTORUN EĞRİSİ (N2O tank boşalması)' ve rozet
    'AZAMİ alfa 3,3 derece' / 'MAX alpha 3.3 deg'."""
    for dil in ('tr', 'en'):
        assert 'N₂O' in _sozluk('sixdof.srcMotorBlowdown', dil)
        assert 'N2O' not in _sozluk('sixdof.srcMotorBlowdown', dil)
        alfa = _sozluk('sixdof.badgeMaxAlpha', dil)
        assert 'α {a}' in alfa and 'alfa' not in alfa and 'alpha' not in alfa
    assert "'ENGINE CURVE (N₂O tank blowdown)'" in PANEL
    assert "'MAX α {a} deg'" in PANEL and "'MAX alpha {a} deg'" not in PANEL
