"""V306/DİL-KATI bekçileri — katı motor sayfasının kullanıcıya görünen dili.

Kilitlenen (kanıt: docs/scofield/raw/OH/V306/dil-kati/RAPOR.md):

1. Katı formunun "?" ipuçları (solid.html ``.tooltip-text`` + i18n_pages.js
   EN/TR) uç adı (``/api/...``, ``/calculate``, ``/analyze``), "olarak
   gönderilir / sent as" kalıbı, ham alan adı (snake_case) ve kaynaksız
   "tipik değer / typically / genellikle" cümlesi taşımaz.
2. Güvenlik sekmesinin kap hükmü rozeti ham kodu (NOT_EVALUATED) basmaz:
   güvertenin Güvenlik paneliyle AYNI sözlük anahtarlarından okunur.
3. Çözücünün sayfada çevrilen sabit cümleleri (ısı açığa çıkma hızı işletme
   noktası, irtifa tablosu ε dayanağı, CAD sekmesi tane/lüle tipi) çözücüde
   hâlâ aynı yazılıyor; değişirse sayfa sözlüğü sessizce devreden çıkmasın
   diye burada düşer.
4. Bu çeviricilerin davranışı (node'da, TR sözlüğüyle): kod → TR metin;
   tanınmayan değer HAM kalır (çeviri uydurulmaz).
"""
import io
import json
import os
import re
import shutil
import subprocess

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SABLON = os.path.join(KOK, 'hrma', 'templates', 'solid.html')
SAYFA_SOZLUK = os.path.join(KOK, 'hrma', 'static', 'js', 'i18n_pages.js')
ORTAK_SOZLUK = os.path.join(KOK, 'hrma', 'static', 'js', 'i18n_common.js')
MOTOR = os.path.join(KOK, 'hrma', 'engines', 'solid_rocket_engine.py')


def _oku(yol):
    with io.open(yol, encoding='utf-8') as fh:
        return fh.read()


def _sozluk(yol, onek):
    """{anahtar: [EN, TR]} — dosyadaki iki bloğun sırasıyla."""
    sonuc = {}
    for m in re.finditer(r"^\s*'(%s[^']+)'\s*:\s*'((?:[^'\\]|\\.)*)'\s*,?\s*$"
                         % re.escape(onek), _oku(yol), re.M):
        sonuc.setdefault(m.group(1), []).append(
            m.group(2).replace("\\'", "'").replace('\\\\', '\\'))
    return sonuc


@pytest.fixture(scope='module')
def ipuclari():
    html = _oku(SABLON)
    anahtarlar = sorted(set(re.findall(
        r'class="tooltip-text"[^>]*data-i18n="(solid\.[^"]+)"', html)))
    sozluk = _sozluk(SAYFA_SOZLUK, 'solid.')
    return anahtarlar, sozluk


UC_ADI = re.compile(r'/api/|/calculate|/analyze|olarak gönderilir|olarak gider|'
                    r'\bsent as\b|\bis sent as\b|\bendpoint\b')
ALAN_ADI = re.compile(r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b')
TIPIK = re.compile(r'\b(?:Typical values|Typical range|typically|Usually|usually|'
                   r'Tipik değerler|Tipik aralık|tipik olarak|genellikle|Genellikle)\b')


def test_ipucu_listesi_bos_degil(ipuclari):
    anahtarlar, sozluk = ipuclari
    assert len(anahtarlar) >= 90, len(anahtarlar)
    eksik = [k for k in anahtarlar if len(sozluk.get(k, [])) != 2]
    assert not eksik, eksik


@pytest.mark.parametrize('desen,ad', [(UC_ADI, 'uç adı / gönderim kalıbı'),
                                      (ALAN_ADI, 'ham alan adı'),
                                      (TIPIK, 'kaynaksız tipik değer')])
def test_ipuclarinda_yasak_kalip_yok(ipuclari, desen, ad):
    anahtarlar, sozluk = ipuclari
    kotu = []
    for k in anahtarlar:
        for dil, metin in zip(('en', 'tr'), sozluk[k]):
            bulunan = desen.findall(metin)
            if bulunan:
                kotu.append((k, dil, bulunan[:3]))
    assert not kotu, '%s: %s' % (ad, kotu[:10])


def test_sablondaki_ipucu_metni_en_sozlukle_ayni(ipuclari):
    """Şablondaki yedek metin EN sözlükle aynı (dil yüklenmezse de aynı cümle)."""
    anahtarlar, sozluk = ipuclari
    html = _oku(SABLON)
    farkli = []
    for k in anahtarlar:
        m = re.search(r'data-i18n="%s">([^<]*)</span>' % re.escape(k), html)
        if m and m.group(1).replace('&quot;', '"') != sozluk[k][0]:
            farkli.append(k)
    # Eski anahtarların bir kısmı yedek metni bilerek ayrı tutabiliyor; bu
    # kulvarın yeniden yazdığı ipuçlarının hiçbiri o listede olmamalı.
    yeniden_yazilan = {
        'solid.ui.performance_reduction_due_to_solid_particles',
        'solid.ui.axial_length_of_individual_propellant_grain',
        'solid.ui.combined_mass_of_forward_and_aft',
        'solid.ui.mass_of_motor_casing_including_forward',
        'solid.ui.mass_of_thermal_insulation_materials_including',
        'solid.ui.c_efficiency_factor_accounts_for_incomplete',
        'solid.ui.factor_of_safety_for_case_design',
        'solid.ui.operating_pressure_in_the_combustion_chamber',
        'solid.ui.outer_diameter_of_the_propellant_grain',
        'solid.ui.initial_wet_mass_kg_help',
    }
    assert not (set(farkli) & yeniden_yazilan), sorted(set(farkli) & yeniden_yazilan)


def test_kap_rozeti_ham_kod_basmaz():
    html = _oku(SABLON)
    bas = html.index('function vesselVerdictHTML(ps)')
    govde = html[bas:html.index('function designFactorCheckRowHTML', bas)]
    assert "esc(kapHukumMetni(durum))" in govde
    assert "+ ';\">' + esc(durum) + '</span>'" not in govde
    ortak = _sozluk(ORTAK_SOZLUK, 'panel.safety.vesselStatus.')
    for kod in ('PASS', 'MARGINAL', 'FAIL', 'NOT_EVALUATED'):
        anahtar = 'panel.safety.vesselStatus.' + kod
        assert ("ortakMetin('%s'" % anahtar) in html, anahtar
        assert len(ortak.get(anahtar, [])) == 2, anahtar
    assert ortak['panel.safety.vesselStatus.NOT_EVALUATED'][1] == 'DEĞERLENDİRİLMEDİ'


def test_sayfanin_cevirdigi_cozucu_cumleleri_cozucude_ayni():
    motor = _oku(MOTOR)
    assert "'peak of the solved burn' if guc else None" in motor
    assert ("'clamped to the 2.5-500 model range; the uncapped optimum '\n"
            "                    'for this altitude is reported separately. The thrust '\n"
            "                    'coefficient and Isp in this row belong to the CLAMPED '\n"
            "                    'nozzle (pressure-thrust term included), not to the '\n"
            "                    'uncapped optimum'") in motor
    assert "'optimum expansion for ambient pressure at this altitude'" in motor
    for ad in ("'type': 'BATES (Cylindrical)'", "'type': 'De Laval Nozzle'",
               "'type': 'End Burner'", "f'Star ({star_points}-pointed)'",
               "'Wagon Wheel (7 cores)'", "f'Finocyl ({n} fins)'",
               "f'Slotted ({n} axial slots)'"):
        assert ad in motor, ad


def _islev(html, ad):
    bas = html.index('        function %s(' % ad)
    son = html.index('\n        }\n', bas) + len('\n        }\n')
    return html[bas:son]


@pytest.mark.skipif(shutil.which('node') is None, reason='node yok')
def test_ceviriciler_tr_metin_verir_taninmayani_ham_birakir():
    html = _oku(SABLON)
    tr = {}
    for yol in (SAYFA_SOZLUK, ORTAK_SOZLUK):
        for k, v in _sozluk(yol, '').items():
            if len(v) == 2:
                tr[k] = v[1]
    kod = '\n'.join(_islev(html, ad) for ad in (
        'kapHukumMetni', 'malzemeAdi', 'taneTipiAdi', 'luleTipiAdi',
        'irtifaEpsDayanagi'))
    betik = (
        'const TR = %s;\n'
        'function T(k, fb) { return Object.prototype.hasOwnProperty.call(TR, k) ? TR[k] : fb; }\n'
        'function TF(k, p, fb) { return T(k, fb).replace(/\\{(\\w+)\\}/g, (w, n) => (n in p ? String(p[n]) : w)); }\n'
        'function ortakMetin(k, fb, d) { return d ? TF(k, d, fb) : T(k, fb); }\n'
        'function numTxt(v, d) { return (d === undefined ? String(v) : v.toFixed(d)).replace(".", ","); }\n'
        'const window = {};\n'
        '%s\n'
        'console.log(JSON.stringify({\n'
        '  kap: kapHukumMetni("NOT_EVALUATED"), kap_pass: kapHukumMetni("PASS"), kap_bilinmeyen: kapHukumMetni("XYZ"),\n'
        '  mat: malzemeAdi("graphite"), mat_kasa: malzemeAdi("steel"), mat_ham: malzemeAdi("Unobtainium 9"),\n'
        '  tane: taneTipiAdi("BATES (Cylindrical)"), yildiz: taneTipiAdi("Star (6-pointed)"),\n'
        '  yiv: taneTipiAdi("Slotted (6 axial slots)"), tane_ham: taneTipiAdi("Moon Burner"),\n'
        '  lule: luleTipiAdi("De Laval Nozzle"),\n'
        '  eps: irtifaEpsDayanagi("clamped to the 2.5-500 model range; the uncapped optimum for this altitude is reported separately. The thrust coefficient and Isp in this row belong to the CLAMPED nozzle (pressure-thrust term included), not to the uncapped optimum"),\n'
        '  eps_opt: irtifaEpsDayanagi("optimum expansion for ambient pressure at this altitude"),\n'
        '  eps_ham: irtifaEpsDayanagi("some other basis")\n'
        '}));\n') % (json.dumps(tr, ensure_ascii=False), kod)
    # Betik stdin'den verilir (test_node_cagri_sozlesmesi: argv tavanı).
    cikti = subprocess.run(['node'], input=betik, capture_output=True, text=True,
                           timeout=60)
    assert cikti.returncode == 0, cikti.stderr[-2000:]
    s = json.loads(cikti.stdout)
    assert s['kap'] == 'DEĞERLENDİRİLMEDİ' and s['kap_pass'] == 'GEÇTİ'
    assert s['kap_bilinmeyen'] == 'XYZ'
    assert s['mat'].startswith('Grafit') and s['mat_kasa'].startswith('Karbon çeliği')
    assert s['mat_ham'] == 'Unobtainium 9'
    assert s['tane'] == 'BATES (Silindirik)' and s['yildiz'] == 'Yıldız (6 uçlu)'
    assert s['yiv'] == 'Yarıklı (6 eksenel yarık)' and s['tane_ham'] == 'Moon Burner'
    assert s['lule'] == 'De Laval nozulu'
    assert s['eps'].startswith('modelin 2,5-500 aralığına kırpıldı')
    assert s['eps_opt'] == 'bu irtifadaki ortam basıncı için optimum genişleme'
    assert s['eps_ham'] == 'some other basis'


def test_yuzde_karti_isaret_yerini_i18n_percentten_alir():
    """C* VERİMİ kartı TR'de '%95,0' (I18N.percent kararı), sabit sonek değil."""
    html = _oku(SABLON)
    assert "String(window.I18N.percent(1, 0)).charAt(0) === '%'" in html
    assert '${onBirim}${countSpan}${sonBirim}' in html
    assert '${countSpan}<small>${m.unit}</small>' not in html


@pytest.mark.skipif(shutil.which('node') is None, reason='node yok')
def test_toplam_kuru_kutle_cozucunun_tam_degerinden():
    """M-KATI-8: alanlar çözücünün 3 ondalıklı değerini gösterirken toplam tam
    değerden kurulur (yuvarlanmışların toplamı 0,864 ⟷ çözücü 0,8646 → 0,865);
    kullanıcının değiştirdiği alan kendi sayısıyla girer."""
    html = _oku(SABLON)
    kod = _islev(html, 'updateTotalMasses')
    betik = (
        'const alan = {};\n'
        'function el(id, deger, tam) { alan[id] = {value: deger, dataset: tam === undefined ? {} : {cozucuDegeri: String(tam), cozucuMetni: deger}}; }\n'
        'const document = {getElementById: (id) => alan[id] || null};\n'
        'el("propellant_mass", "1.629", 1.6293446627841826);\n'
        'el("case_mass", "0.437", 0.43712); el("nozzle_mass", "0.042", 0.04211);\n'
        'el("insulation_mass", "0.115", 0.11512); el("liner_mass", "0.111", 0.11112);\n'
        'el("closure_mass", "0.159", 0.15913); el("dry_mass", ""); el("wet_mass", "");\n'
        '%s\n'
        'updateTotalMasses(); const a = [alan.dry_mass.value, alan.wet_mass.value];\n'
        'alan.case_mass.value = "0.500"; updateTotalMasses();\n'
        'console.log(JSON.stringify({tam: a, elle: alan.dry_mass.value}));\n') % kod
    cikti = subprocess.run(['node'], input=betik, capture_output=True, text=True, timeout=60)
    assert cikti.returncode == 0, cikti.stderr[-2000:]
    s = json.loads(cikti.stdout)
    # tam toplam 0,8646 → '0.865' (yuvarlanmışların toplamı 0,864 olurdu)
    assert s['tam'] == ['0.865', '2.494'], s
    # elle değiştirilen kasa (0,500) kendi sayısıyla: 0,500 + 0,04211 + 0,11512 + 0,11112 + 0,15913
    assert s['elle'] == '0.927', s


@pytest.mark.skipif(shutil.which('node') is None, reason='node yok')
def test_ateslemesistemi_ve_yakit_anahtari_tr():
    """Güvenlik sekmesi 'Electric match' ve UYARILAR'daki yakıt/yasa anahtarı
    ('kndx', 'sugar') TR ekranda sözlükten; tanınmayan değer ham."""
    html = _oku(SABLON)
    motor = _oku(MOTOR)
    assert "'ignition_system': 'Electric match'," in motor
    assert "'warn.solid.piecewise_law_active', 'info'" in motor
    assert "'warn.solid.propellant_secondary_inherited', 'info'" in motor
    tr = {}
    for k, v in _sozluk(SAYFA_SOZLUK, 'solid.').items():
        if len(v) == 2:
            tr[k] = v[1]
    kod = '\n'.join(_islev(html, ad) for ad in ('yakitAdi', 'ateslemeSistemiAdi'))
    betik = (
        'const TR = %s;\n'
        'function T(k, fb) { return Object.prototype.hasOwnProperty.call(TR, k) ? TR[k] : fb; }\n'
        '%s\n'
        'console.log(JSON.stringify({kndx: yakitAdi("kndx"), sugar: yakitAdi("sugar"), ham: yakitAdi("zzz_yok"),\n'
        '  ates: ateslemeSistemiAdi("Electric match"), ates_ham: ateslemeSistemiAdi("Pyrogen")}));\n'
    ) % (json.dumps(tr, ensure_ascii=False), kod)
    cikti = subprocess.run(['node'], input=betik, capture_output=True, text=True, timeout=60)
    assert cikti.returncode == 0, cikti.stderr[-2000:]
    s = json.loads(cikti.stdout)
    assert s['kndx'].startswith('KNDX - Potasyum Nitrat') and s['sugar'].startswith('KNSU')
    assert s['ham'] == 'zzz_yok'
    assert s['ates'] == 'Elektrikli ateşleyici (e-match)' and s['ates_ham'] == 'Pyrogen'
    bas = html.index('function displaySolidWarnings(results)')
    govde = html[bas:bas + 12000]
    assert '(YAKIT_PARAMETRELERI[w.code] || []).indexOf(k) !== -1' in govde
    assert 'p[k] = yakitAdi(v);' in govde and 'p[k] = malzemeAdi(v);' in govde
    assert "if (k === 'material' && typeof v === 'string')" in govde


def test_tr_ekranda_mesh_degil_ag():
    """D7 (ana model kararı, 9 Kas akşam): TR'de FEA terimi "AĞ"; ortak FEA anahtarları ile
    solid.fea.* aynı karşılık (test_z5i18n_supurme). Ham 'mesh.meta:' öneki ve
    '(kalinlik_sapma_orani)' alan adı iki dilde de yok."""
    onekler = ('fea.', 'feaT.', 'panel.fea.', 'panel.feaT.', 'panel.grain.', 'solid.fea.')
    kotu = []
    for yol, onek in ((ORTAK_SOZLUK, ''), (SAYFA_SOZLUK, 'solid.fea.')):
        for k, v in _sozluk(yol, onek).items():
            if not k.startswith(onekler) or len(v) != 2:
                continue
            en, tr = v
            tr_metin = re.sub(r'\{[^}]*\}', '', tr)
            if re.search(r'\b(MESH|Mesh|mesh)\b', tr_metin):
                kotu.append((k, 'tr', tr[:80]))
            for dil, metin in (('en', en), ('tr', tr)):
                if 'mesh.meta' in metin or 'kalinlik_sapma_orani' in metin:
                    kotu.append((k, dil, metin[:80]))
    assert not kotu, kotu[:10]
    ortak = _sozluk(ORTAK_SOZLUK, 'fea.')
    sayfa = _sozluk(SAYFA_SOZLUK, 'solid.fea.')
    assert ortak['fea.badgeMesh'][1] == sayfa['solid.fea.badge_mesh'][1] == 'AĞ {elems} eleman / {nodes} düğüm'


def test_termal_panel_ipuclari_ve_http_yedegi():
    """TERMAL-KONTUR DEVİR (2. tur): panel.thermal.help.* ipuçlarında uç/alan adı yok;
    termal panelin eksenel profil reddinde kullanıcı metnine HTTP kodu ortak ret yedeğinden."""
    kotu = []
    for k, v in _sozluk(ORTAK_SOZLUK, 'panel.thermal.help.').items():
        for dil, metin in zip(('en', 'tr'), v):
            bul = re.findall(r'/api/|/analyze|wall_layers|\bendpoint\b|\buç\b|repository validator|'
                             r'depo doğrulayıcı|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b', metin)
            bul = [b for b in bul if b not in ('x_h2o', 'x_co2')]
            if bul:
                kotu.append((k, dil, bul[:3]))
    assert not kotu, kotu
    panel = _oku(os.path.join(KOK, 'hrma', 'static', 'js', 'panels', 'thermal_panel.js'))
    assert "throw new Error((data && data.error) || ('HTTP ' + resp.status));" not in panel
    assert 'window.HRMAReject.yedek(resp.status)' in panel
