"""V301/HİBRİT-DIŞA (28 Eki) — kalem 3 (uçan atıl kütle adı), kalem 4 (kazanılmamış
plaka uyarısının TR çevirisi), kalem 5 (eksik "?" açıklamaları) statik bekçileri.

Kalem 1 bekçisi tarayıcıdadır (tests/test_v301_proje_gidis_donus.py); kalem 2 KABUL
K4'te (tests/test_v301_kabul.py::test_k4_paket_eng_dugmeyle_ayni); kalem 4 API
iddiaları tests/test_d20_app_api_a1.py::TestP15B1_02PlakaKalinligi'nde.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
TPL = ROOT / 'hrma' / 'templates'
JS = ROOT / 'hrma' / 'static' / 'js'


def oku(p):
    return pathlib.Path(p).read_text(encoding='utf-8')


def sozluk_degeri(metin, anahtar, blok):
    """i18n dosyasında anahtarın EN (blok=0) / TR (blok=1) değeri."""
    bulunan = re.findall(r"'" + re.escape(anahtar) + r"':\s*'((?:[^'\\]|\\.)*)'", metin)
    assert len(bulunan) == 2, (anahtar, len(bulunan))
    return bulunan[blok].encode('utf-8').decode('unicode_escape').encode('latin-1').decode('utf-8') \
        if '\\u' in bulunan[blok] else bulunan[blok]


# --- kalem 5 -----------------------------------------------------------------
YENI_IPUCLARI = ('adv.tip.calculateTrajectory', 'adv.tip.chamberLengthOverrideMm')


def test_hibrit_iki_alanin_ipucu_isaretlemede_ve_sozlukte():
    html = oku(TPL / 'advanced.html')
    sozluk = oku(JS / 'i18n_advanced.js')
    for alan, anahtar in (('calculate_trajectory', 'adv.tip.calculateTrajectory'),
                          ('chamber_length_override', 'adv.tip.chamberLengthOverrideMm')):
        i = html.index('id="%s"' % alan)
        grup_bas = html.rfind('<div class="form-group"', 0, i)
        grup = html[grup_bas:html.index('</div>\n', i) + 6]
        assert 'tooltip-icon' in html[grup_bas:i + 2000] and anahtar in html[grup_bas:i + 2000], alan
        en, tr = sozluk_degeri(sozluk, anahtar, 0), sozluk_degeri(sozluk, anahtar, 1)
        assert en and tr and en != tr, anahtar
        assert any(ch in tr for ch in 'çğıöşüİ'), anahtar
    # label'daki data-i18n ipucunu silerdi: etiket metni iç <span>'da
    assert '<label for="chamber_length_override" data-i18n' not in html


def test_ipucu_icerigi_koddaki_kabul_araligiyla_ayni():
    """chamber_length_override: 0/boş = otomatik, > 20 m uygulanmaz (motor kodu)."""
    motor = oku(ROOT / 'hrma' / 'engines' / 'hybrid_rocket_engine.py')
    assert 'if L > 20.0:' in motor and 'if L <= 0:' in motor
    en = sozluk_degeri(oku(JS / 'i18n_advanced.js'), 'adv.tip.chamberLengthOverrideMm', 0)
    assert '20000 mm (20 m)' in en and 'Empty or 0' in en


def test_ls_time_kaydiricisi_ipucuyla_iliskili():
    html = oku(TPL / 'launch_site.html')
    i = html.index('id="ls-time"')
    sar = html.rfind('<label class="ls-timewrap"', 0, i)
    assert sar > 0 and html.index('</label>', i) > html.index('id="ls-time-help"', i)
    assert 'aria-describedby="ls-time-help"' in html[i - 40:i + 120]


# --- kalem 3 -----------------------------------------------------------------
def test_ucan_atil_kutle_etiketi_kunyeyle_ayni_ad():
    sozluk = oku(JS / 'i18n_launch_site.js')
    assert "'site.vInertMass': 'Flying inert mass (kg)'" in sozluk
    assert "'site.vInertMass': 'Uçan atıl kütle (kg)'" in sozluk
    # künye (flight_vehicle._liquid_inert_mass) ve TR çevirisi aynı adı taşır
    assert "'flying inert mass = '" in oku(ROOT / 'hrma' / 'analysis' / 'flight_vehicle.py')
    assert "'uçan atıl kütle = '" in oku(JS / 'i18n_charts.js')
    html = oku(TPL / 'launch_site.html')
    assert 'Engine inert (kg)' not in html and 'engine inert mass shown above' not in html
    assert 'motor atıl kütlesi' not in sozluk.lower()


# --- kalem 4 -----------------------------------------------------------------
def test_kazanilmamis_plaka_uyarisinin_tr_cevirisi_var():
    from hrma.utils.injector_design import LD_NOT_ISSUED_WARNING
    charts = oku(JS / 'i18n_charts.js')
    desenler = re.findall(r"\[/\^(L\\/D band check NOT ISSUED[^\n]*?)\$/,", charts)
    js_to_py = [d.replace('\\/', '/') for d in desenler]
    assert any(re.fullmatch(d, LD_NOT_ISSUED_WARNING) for d in js_to_py), js_to_py
    assert not re.search(r'\d', LD_NOT_ISSUED_WARNING.replace('3-5', '')), (
        'uyarı kazanılmamış plakadan sayı taşımamalı')


# --- ortak: kullanıcıya görünen yeni metinlerde ilke cümlesi yok -------------
def test_yeni_metinlerde_ilke_cumlesi_yok():
    yasak = re.compile(r'invent|uydur|temel ilke|does not make up', re.I)
    sozluk_adv = oku(JS / 'i18n_advanced.js')
    sozluk_ls = oku(JS / 'i18n_launch_site.js')
    metinler = [sozluk_degeri(sozluk_adv, k, b) for k in YENI_IPUCLARI for b in (0, 1)]
    metinler += [sozluk_degeri(sozluk_ls, k, b) for k in ('site.help.vInertMass', 'site.vInertMass')
                 for b in (0, 1)]
    from hrma.utils.injector_design import LD_NOT_ISSUED_WARNING
    metinler.append(LD_NOT_ISSUED_WARNING)
    for m in metinler:
        assert not yasak.search(m), m
