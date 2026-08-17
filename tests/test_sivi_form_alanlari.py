"""Sıvı form kapıları + Isp/ısı-akısı adlandırma bekçileri (v2.6.27, A5).

İki borç tek dosyada kilitlenir çünkü ikisi de aynı dosya kümesine dokunur
(liquid.html / advanced.html / solid.html / i18n_pages.js):

1. "KANAL VAR KAPI YOK" SINIFI. Motor yedi girdiyi ZATEN okuyordu
   (closure_bolt_count/size/class, feed_line_wall_thickness,
   valve_closure_time_ms, feed_line_material, pressurization_type) ama
   liquid.html'de alanları yoktu: kullanıcı bu kanalları yalnız API'den
   besleyebiliyordu. Alanlar eklendi; bu dosya üç şeyi kilitler:
   (a) boş alan payload'a GİRMEZ (gerçek toplayıcı node üzerinde koşturulur),
   (b) dolu alan /calculate_liquid üzerinden çıktıyı GERÇEKTEN değiştirir
       ya da beyanla yankılanır (uçtan uca),
   (c) motorda okunan-formda olmayan anahtar listesi BOŞ kalır (yapısal
       tarama; yeni bir kanal açılırsa burası kırılır).

   NOT: yeni alanlar BİLEREK ``collectAllParameters()`` DIŞINDA, ayrı bir
   toplayıcıda (``collectClosureAndFeedLineParams``) durur.
   tests/test_liquid_input_wiring.py'nin sarsım tablosu o fonksiyonun
   gövdesine kilitlidir ve bu iş kaleminde düzenlenemez kapsam dışındaydı;
   yeni alanların sarsım kanıtı bu dosyadaki uçtan uca testlerdir.

2. Isp / ISI AKISI ADLANDIRMASI. Aynı yanıt birden çok, ayrı tanımlı "Isp"
   taşır (tasarım noktası, vakum, deniz seviyesi, irtifada teslim edilen,
   anlık, kütle bütçesinin ima ettiği) ve iki ayrı "boğaz ısı akısı" vardır
   (referans soğutulmuş cidardaki tasarım yükü ile denge cidarındaki akı;
   2,5 kat fark). Şablonlar bunları çıplak 'Isp' / 'Specific Impulse' /
   'Heat Flux' etiketiyle basıyordu. Etiketler tanımlı adlara çevrildi;
   buradaki tarama üç şablonda çıplak etiketin geri gelmesini engeller.

   Bilinçli kalan açık (bulgu defterinde kayıtlı): i18n_common.js ortak
   sözlüğündeki app.metric.isp / panel.thermal.cardQThroat /
   panel.thermal.heatFluxSeries / panel.regen.cardPeakFlux etiketleri —
   o dosya bu iş kaleminde dokunulamaz kapsam dışıydı.
"""

import copy
import json
import math
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

from hrma.app import app
from tests.test_liquid_input_wiring import BASE_PAYLOAD

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'
ENGINE_PY = REPO_ROOT / 'hrma' / 'engines' / 'liquid_rocket_engine.py'
I18N_PAGES = REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n_pages.js'
I18N_ADVANCED = REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n_advanced.js'

LOCAL_HOST = {'Host': '127.0.0.1:8080'}

#: A5 (+ parti 28 chug atalet kapıları) ile eklenen alanlar:
#: id == payload anahtarı.
YENI_SAYISAL_ALANLAR = ('closure_bolt_count', 'feed_line_wall_thickness',
                        'valve_closure_time_ms', 'feed_line_length_m',
                        'feed_line_diameter_mm')
YENI_SECIM_ALANLARI = ('closure_bolt_size', 'closure_bolt_class',
                       'feed_line_material', 'pressurization_type')

#: Motorun okuduğu ama formda BİLEREK alanı olmayan anahtarlar.
#: Her satır gerekçelidir; gerekçesiz genişletmek bu bekçiyi anlamsızlaştırır.
BILINCLI_ISTISNALAR = {
    # liquid.html (collectAllParameters, 2026-07-23 notu): çözücü optimum
    # O/F'yi gerçek Pc'de CEA taramasıyla KENDİSİ bulur; elle girilen değer
    # hesabı etkilemediği için alan ölü girdi olurdu. Kanal API/proje
    # yüklemesi için açık tutulur ama sayfada kapısı bilinçli olarak yok.
    'of_max_isp',
    'of_max_thrust',
    # Parti 28: hat ataleti için formda İÇ ÇAP sorulur
    # (feed_line_diameter_mm) ve akış alanı motorda ondan dairesel kesitle
    # türetilir (liquid_rocket_engine._feed_line_inertance_inputs). Aynı
    # büyüklük için ikinci bir alan (alan m²) formda dursaydı iki girdi
    # birbiriyle çelişebilirdi; bu kanal dairesel olmayan kanallar için
    # API/proje yüklemesine açık tutulur ama sayfada kapısı bilinçli yok.
    'feed_line_area_m2',
}


def read(path):
    return path.read_text(encoding='utf-8')


def mask_comments(text):
    """HTML/JS yorumlarını ve <style> bloklarını boşlukla maskeler.

    Satır içi '//' bilerek KESİLMEZ (URL'ler ve string içi '//' güvenliği);
    yalnız tam-satır JS yorumları maskelenir — test_liquid_page_contract.py
    ile aynı yaklaşım.
    """
    out = list(text)
    patterns = [r'<!--[\s\S]*?-->', r'<style[\s\S]*?</style>',
                r'/\*[\s\S]*?\*/', r'(?m)^[ \t]*//[^\n]*$']
    for pat in patterns:
        for m in re.finditer(pat, text):
            for i in range(m.start(), m.end()):
                if out[i] != '\n':
                    out[i] = ' '
    return ''.join(out)


# ---------------------------------------------------------------------------
# Yardımcılar: yanıt ağacı
# ---------------------------------------------------------------------------
def _leaves(obj, prefix='$'):
    out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.update(_leaves(value, '%s.%s' % (prefix, key)))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            out.update(_leaves(value, '%s[%d]' % (prefix, index)))
    else:
        out[prefix] = obj
    return out


def _find_nodes(obj, key):
    """Ağaçta adı ``key`` olan tüm düğümlerin değerleri."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                found.append(v)
            found.extend(_find_nodes(v, key))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(_find_nodes(v, key))
    return found


def _same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        fa, fb = float(a), float(b)
        if math.isnan(fa) and math.isnan(fb):
            return True
        return math.isclose(fa, fb, rel_tol=1e-9, abs_tol=0.0)
    return a == b


def _changed(before, after):
    return [p for p in sorted(set(before) | set(after))
            if p not in before or p not in after
            or not _same(before[p], after[p])]


@pytest.fixture(scope='module')
def client():
    return app.test_client()


def _calculate(client, payload):
    resp = client.post('/calculate_liquid', json=payload, headers=LOCAL_HOST)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    assert not body.get('error'), body.get('error')
    return body


@pytest.fixture(scope='module')
def taban(client):
    """Yeni alanların HİÇBİRİ olmadan taban koşu (form boş bırakılmış gibi)."""
    return _calculate(client, copy.deepcopy(BASE_PAYLOAD))


# ---------------------------------------------------------------------------
# 1a. Şablon deseni: alanlar boş, sayı dayatmıyor
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('alan', YENI_SAYISAL_ALANLAR)
def test_sayisal_alan_bos_varsayilanla_var(alan):
    """Sayısal alan value="" ile durur; sayfa varsayılan sayı DAYATMAZ."""
    html = read(LIQUID_HTML)
    m = re.search(r'<input[^>]*id="%s"[^>]*>' % re.escape(alan), html)
    assert m, '%s alanı liquid.html\'de yok' % alan
    assert 'value=""' in m.group(0), (
        '%s alanı boş varsayılanla durmalı (2,3x dersi: sayfa sayı '
        'dayatmaz): %s' % (alan, m.group(0)))


@pytest.mark.parametrize('alan', YENI_SECIM_ALANLARI)
def test_secim_alani_var(alan):
    html = read(LIQUID_HTML)
    assert re.search(r'<select[^>]*id="%s"' % re.escape(alan), html), (
        '%s seçim alanı liquid.html\'de yok' % alan)


def test_hat_ve_gaz_secimlerinin_varsayilani_bos():
    """Hat malzemesi / basınçlandırma: varsayılan seçenek BOŞ değerlidir.

    Motor bu iki anahtarda 'verilmedi' durumunu ayrıca BEYAN eder
    ("'ss_304' assumed" / 'auto'); sayfa her koşuda bir değer gönderseydi
    o beyan yalan olurdu.
    """
    html = read(LIQUID_HTML)
    for alan in ('feed_line_material', 'pressurization_type'):
        blok = re.search(r'<select[^>]*id="%s".*?</select>' % alan, html, re.S)
        assert blok, alan
        assert re.search(r'<option value="" selected', blok.group(0)), (
            '%s seçiminin varsayılanı boş ("") olmalı' % alan)


def test_civata_secimleri_motor_varsayilaniyla_ayni():
    """Cıvata boyut/sınıf varsayılanı motorun kendi sözleşme değerleri.

    (LIQUID_CLOSURE_JOINT_DEFAULTS: M8 / 8.8 — solid.html ile aynı desen.)
    """
    html = read(LIQUID_HTML)
    assert re.search(r'<option value="M8" selected>', html)
    assert re.search(r'<option value="8.8" selected>', html)


def test_toplayici_cagri_yerinde_birlesiyor():
    """Yeni toplayıcı fetch gövdesinde ana toplayıcıyla birleşir."""
    html = read(LIQUID_HTML)
    assert 'function collectClosureAndFeedLineParams()' in html
    assert 'Object.assign(collectAllParameters(),' in html
    assert 'collectClosureAndFeedLineParams()))' in html


def _toplayici_govdesi():
    html = read(LIQUID_HTML)
    bas = html.index('function collectClosureAndFeedLineParams()')
    son = html.index('\n        }', bas)
    return html[bas:son + len('\n        }')]


def _node_ile_topla(alan_degerleri):
    """GERÇEK toplayıcıyı node üzerinde koşturur, JSON payload döndürür."""
    node = shutil.which('node')
    if not node:                                    # pragma: no cover
        pytest.skip('node yok')
    script = (
        'const FIELDS = %s;\n'
        'global.document = { getElementById: (id) => ('
        'Object.prototype.hasOwnProperty.call(FIELDS, id) '
        '? { value: FIELDS[id] } : null) };\n'
        '%s\n'
        'process.stdout.write(JSON.stringify('
        'collectClosureAndFeedLineParams()));\n'
        % (json.dumps(alan_degerleri), _toplayici_govdesi()))
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                     encoding='utf-8') as fh:
        fh.write(script)
        yol = fh.name
    try:
        proc = subprocess.run([node, yol], capture_output=True, text=True,
                              timeout=60)
    finally:
        pathlib.Path(yol).unlink(missing_ok=True)
    assert proc.returncode == 0, 'node hatası:\n%s' % proc.stderr[:1500]
    return json.loads(proc.stdout)


BOS_FORM = {
    'closure_bolt_count': '', 'closure_bolt_size': 'M8',
    'closure_bolt_class': '8.8', 'feed_line_wall_thickness': '',
    'valve_closure_time_ms': '', 'feed_line_material': '',
    'pressurization_type': '',
    'feed_line_length_m': '', 'feed_line_diameter_mm': '',
}


def test_bos_form_payloada_hicbir_anahtar_koymaz():
    """(a) Boş alan payload'a GİRMEZ — gerçek toplayıcı koşturularak."""
    assert _node_ile_topla(BOS_FORM) == {}


def test_dolu_form_yedi_anahtari_da_tasir():
    dolu = {
        'closure_bolt_count': '12', 'closure_bolt_size': 'M10',
        'closure_bolt_class': '10.9', 'feed_line_wall_thickness': '2.5',
        'valve_closure_time_ms': '350', 'feed_line_material': 'aluminum_6061',
        'pressurization_type': 'nitrogen',
    }
    assert _node_ile_topla(dolu) == {
        'closure_bolt_count': 12, 'closure_bolt_size': 'M10',
        'closure_bolt_class': '10.9', 'feed_line_wall_thickness': 2.5,
        'valve_closure_time_ms': 350, 'feed_line_material': 'aluminum_6061',
        'pressurization_type': 'nitrogen',
    }


def test_civata_secimi_sayisiz_gonderilmez():
    """Cıvata sayısı yokken boyut/sınıf yankısı da payload'a girmez."""
    form = dict(BOS_FORM, closure_bolt_size='M16', closure_bolt_class='12.9')
    assert _node_ile_topla(form) == {}


# ---------------------------------------------------------------------------
# 1b. Uçtan uca: dolu alan çıktıyı değiştiriyor / beyanla yankılanıyor
# ---------------------------------------------------------------------------
def test_civata_sayisi_birlesimi_boyutlandiriyor(client, taban):
    """closure_bolt_* /calculate_liquid üzerinden birleşimi kurar."""
    joints = _find_nodes(taban, 'closure_joint')
    assert joints, 'yanıtta closure_joint bloğu yok'
    assert joints[0].get('status') == 'not_sized', (
        'cıvata sayısı yokken birleşim boyutlandırılmamalı (sayı uydurma '
        'yasağı): %s' % joints[0].get('status'))

    yuk = copy.deepcopy(BASE_PAYLOAD)
    yuk.update({'closure_bolt_count': 12, 'closure_bolt_size': 'M10',
                'closure_bolt_class': '10.9'})
    dolu = _find_nodes(_calculate(client, yuk), 'closure_joint')[0]
    assert dolu.get('status') == 'sized'
    assert dolu.get('bolt_count') == 12
    assert dolu.get('bolt_size') == 'M10'
    assert dolu.get('property_class') == '10.9'
    assert isinstance(dolu.get('proof_safety_factor'), (int, float))


def _su_kocu(yanit):
    """Ana su koçu bloğu.

    Doğrudan yol kullanılır: valve_feedline hat blokları İÇİNDE de
    'water_hammer' adlı (kuplaj) bir alan var; ada göre arama yanlış düğümü
    yakalar (ölçüldü: ilk bulunan null çıkıyor).
    """
    blok = (yanit.get('detailed_feed_system') or {}).get('water_hammer')
    assert isinstance(blok, dict) and blok, (
        'yanıtta detailed_feed_system.water_hammer bloğu yok')
    return blok


def test_hat_cidari_su_kocunu_modelliyor(client, taban):
    """feed_line_wall_thickness yokken su koçu NOT_MODELLED, varken sayı."""
    duz = _leaves(_su_kocu(taban))
    assert any(v == 'NOT_MODELLED' for v in duz.values()), (
        'cidar kalınlığı yokken hat bloğu NOT_MODELLED olmalı (sayı '
        'uydurulmaz)')
    assert any('feed_line_wall_thickness' in str(v) for v in duz.values()), (
        'NOT_MODELLED beyanı eksik girdinin ADINI söylemeli')

    yuk = copy.deepcopy(BASE_PAYLOAD)
    yuk['feed_line_wall_thickness'] = 2.0
    wh_dolu = _su_kocu(_calculate(client, yuk))
    degisen = _changed(duz, _leaves(wh_dolu))
    assert degisen, ('cidar kalınlığı girildi ama su koçu bloğunda hiçbir '
                     'yaprak oynamadı — kanal kopuk')


def test_vana_kapanma_suresi_darbeyi_degistiriyor(client):
    """valve_closure_time_ms (cidar sabitken) su koçu/vana çıktısını oynatır."""
    yuk1 = copy.deepcopy(BASE_PAYLOAD)
    yuk1['feed_line_wall_thickness'] = 2.0
    yuk2 = copy.deepcopy(yuk1)
    yuk2['valve_closure_time_ms'] = 5000.0
    once = _leaves(_calculate(client, yuk1))
    sonra = _leaves(_calculate(client, yuk2))
    degisen = _changed(once, sonra)
    assert degisen, 'vana kapanma süresi hiçbir yaprağı oynatmadı'
    assert any('water_hammer' in p or 'valve' in p for p in degisen), (
        'değişim su koçu / vana bloklarında görünmüyor: %s' % degisen[:10])


def test_hat_malzemesi_okunuyor(client):
    """feed_line_material dalga hızını/beyanı değiştirir, adı yankılanır."""
    yuk1 = copy.deepcopy(BASE_PAYLOAD)
    yuk1['feed_line_wall_thickness'] = 2.0
    yuk2 = copy.deepcopy(yuk1)
    yuk2['feed_line_material'] = 'aluminum_6061'
    once = _calculate(client, yuk1)
    sonra = _calculate(client, yuk2)
    assert _changed(_leaves(_su_kocu(once)), _leaves(_su_kocu(sonra))), (
        'hat malzemesi su koçu bloğunda hiçbir yaprağı oynatmadı')
    assert any('aluminum_6061' in str(v)
               for v in _leaves(_su_kocu(sonra)).values()), (
        'seçilen hat malzemesi yanıtta adıyla görünmüyor')


def test_hat_atalet_kapilari_chug_cevrimine_ulasiyor(client, taban):
    """feed_line_length_m + feed_line_diameter_mm chug çevrimini oynatır.

    Parti 28 kapıları süs değildir: dolu alan, çevrimi ikinci mertebe (hat
    ataletli) forma geçirmeli ve çıktıda yaprak oynatmalıdır. Örnek değerler
    tests/test_stability_sivi.py'nin motor-tarafı bekçisiyle aynıdır
    (1,5 m / 12 mm).
    """
    yuk = copy.deepcopy(BASE_PAYLOAD)
    yuk['feed_line_length_m'] = 1.5
    yuk['feed_line_diameter_mm'] = 12.0
    sonra = _calculate(client, yuk)
    degisen = _changed(_leaves(taban), _leaves(sonra))
    assert degisen, ('hat uzunluğu + iç çapı girildi ama hiçbir yaprak '
                     'oynamadı — kanal kopuk')
    assert any('chug' in p or 'feed_line' in p for p in degisen), (
        'değişim chug/hat bloklarında görünmüyor: %s' % degisen[:10])


def test_basinclandirma_gazi_emniyet_vanasina_ulasiyor(client, taban):
    """pressurization_type=nitrogen tahliye gazını ve vana boyutunu değiştirir."""
    gaz_taban = _find_nodes(taban, 'relieving_gas')
    assert gaz_taban and set(gaz_taban) == {'helium'}, (
        'taban koşuda tahliye gazı helyum olmalı (auto): %s' % gaz_taban)
    yuk = copy.deepcopy(BASE_PAYLOAD)
    yuk['pressurization_type'] = 'nitrogen'
    sonra = _calculate(client, yuk)
    gaz_sonra = _find_nodes(sonra, 'relieving_gas')
    assert gaz_sonra and set(gaz_sonra) == {'nitrogen'}, (
        'nitrogen seçimi tahliye gazına ulaşmadı: %s' % gaz_sonra)


# ---------------------------------------------------------------------------
# 1c. Yapısal tarama: motorda okunan-formda olmayan anahtar listesi BOŞ
# ---------------------------------------------------------------------------
def _motor_anahtarlari():
    src = read(ENGINE_PY)
    keys = set(re.findall(r"_override_(?:val|choice)\(\s*'([a-z_0-9]+)'", src))
    keys |= set(re.findall(r"overrides\.get\(\s*'([a-z_0-9]+)'", src))
    return keys


def _form_alan_idleri():
    html = read(LIQUID_HTML)
    return set(re.findall(r'<(?:input|select)[^>]*\bid="([A-Za-z_0-9]+)"',
                          html))


def test_motorda_okunan_her_anahtarin_formda_kapisi_var():
    """Yeni bir override kanalı açılır da formda kapısı unutulursa kırılır."""
    eksik = _motor_anahtarlari() - _form_alan_idleri() - BILINCLI_ISTISNALAR
    assert not eksik, (
        'Motor şu anahtarları okuyor ama liquid.html\'de alanları yok '
        '(kanal var kapı yok): %s — alan ekleyin ya da gerekçesiyle '
        'BILINCLI_ISTISNALAR listesine yazın' % sorted(eksik))


def test_yapisal_tarama_gercekten_anahtar_goruyor():
    """Negatif kontrol: tarama boş küme döndürüyorsa bekçi köreldi demektir."""
    keys = _motor_anahtarlari()
    assert {'closure_bolt_count', 'feed_line_wall_thickness',
            'valve_closure_time_ms', 'feed_line_material',
            'pressurization_type'} <= keys, (
        'tarama motorun bilinen anahtarlarını görmüyor — regex çürümüş '
        'olabilir: %d anahtar bulundu' % len(keys))
    assert len(keys) > 30


def test_bilincli_istisnalar_hala_motorda_okunuyor():
    """İstisna listesi çürümesin: motor artık okumuyorsa satır silinmeli."""
    olu = BILINCLI_ISTISNALAR - _motor_anahtarlari()
    assert not olu, ('istisna listesinde motorun artık okumadığı anahtar '
                     'var: %s' % sorted(olu))


# ---------------------------------------------------------------------------
# 2. Isp / ısı akısı adlandırması: çıplak etiket kalmadı
# ---------------------------------------------------------------------------
#: Tanımsız (çıplak) etiketler: tek başına hangi Isp/akı olduğunu söylemezler.
CIPLAK_ISP = {'Isp', 'Isp (s)', 'Specific Impulse', 'Specific impulse',
              'Specific impulse (s)', 'Specific Impulse (s)',
              'Specific Impulse (Isp)'}
CIPLAK_AKI = {'Heat Flux', 'Heat flux', 'HEAT FLUX'}

UC_SAYFA = ('advanced.html', 'solid.html', 'liquid.html')


def _ciplak_etiketler(text, yasakli):
    """Maskelemeden SONRA kalan, yasaklı kümeye birebir eşit metinler.

    İki biçim taranır: tırnaklı string literalleri (T()/i18nText()
    yedekleri, tablo etiketleri, dizi elemanları) ve HTML düğüm metinleri
    (>Isp< biçimi).
    """
    bulgular = []
    for m in re.finditer(r"'([^'\\\n]*)'|\"([^\"\\\n]*)\"", text):
        deger = m.group(1) if m.group(1) is not None else m.group(2)
        if deger in yasakli:
            satir = text.count('\n', 0, m.start()) + 1
            bulgular.append('%d: %r' % (satir, deger))
    for m in re.finditer(r'>\s*([^<>]+?)\s*<', text):
        if m.group(1) in yasakli:
            satir = text.count('\n', 0, m.start()) + 1
            bulgular.append('%d: >%s<' % (satir, m.group(1)))
    return bulgular


@pytest.mark.parametrize('sayfa', UC_SAYFA)
def test_ciplak_isp_etiketi_kalmadi(sayfa):
    """Bulgu defteri kapanışı: 'Isp' hangi Isp olduğunu söylemeden basılmaz."""
    text = mask_comments(read(TEMPLATES / sayfa))
    bulgu = _ciplak_etiketler(text, CIPLAK_ISP)
    assert not bulgu, (
        '%s içinde çıplak Isp etiketi geri gelmiş (tanımlı ek kullanın, '
        'ör. "Isp (design point, ...)", "Vacuum Isp", "Isp (sea level)"): '
        '\n  %s' % (sayfa, '\n  '.join(bulgu)))


@pytest.mark.parametrize('sayfa', UC_SAYFA)
def test_ciplak_isi_akisi_etiketi_kalmadi(sayfa):
    """İki ayrı boğaz akısı (referans cidar / denge cidarı) tek adı paylaşamaz."""
    text = mask_comments(read(TEMPLATES / sayfa))
    bulgu = _ciplak_etiketler(text, CIPLAK_AKI)
    assert not bulgu, (
        '%s içinde çıplak ısı akısı etiketi geri gelmiş (cidar referansını '
        'yazın, ör. "Throat Heat Flux (at design wall temperature)"):\n  %s'
        % (sayfa, '\n  '.join(bulgu)))


def test_ciplak_etiket_tarayicisi_calisiyor():
    """Negatif kontrol: tarayıcı bilinen çıplak biçimleri gerçekten yakalar."""
    ornek = "row(T('x.y', 'Isp'), v) + '<td>' \n<div>Heat Flux</div>"
    assert _ciplak_etiketler(ornek, CIPLAK_ISP) == ["1: 'Isp'"]
    assert _ciplak_etiketler(ornek, CIPLAK_AKI) == ['2: >Heat Flux<']
    # Tanımlı ekler yakalanmaz (yanlış pozitif üretmez):
    temiz = "T('x', 'Isp (sea level)') + T('y', 'Vacuum Isp (s)')"
    assert _ciplak_etiketler(temiz, CIPLAK_ISP) == []


def _sozluk_degeri(path, anahtar):
    m = re.search(r"'%s':\s*'([^'\n]*)'" % re.escape(anahtar), read(path))
    assert m, '%s içinde %s yok' % (path.name, anahtar)
    return m.group(1)


@pytest.mark.parametrize('anahtar', [
    'liq.msg.specific_impulse', 'liq.msg.specific_impulse_isp',
    'liq.msg.specific_impulse_s', 'liq.msg.heat_flux',
    'solid.msg.isp_s', 'solid.msg.isp_distribution',
    'solid.msg.isp_sea_level_mc', 'solid.msg.specific_impulse_s',
])
def test_sayfa_sozlugundeki_etiketler_tanimli(anahtar):
    """Sözlük değeri de çıplak kalamaz (görünen metin sözlükten gelir)."""
    deger = _sozluk_degeri(I18N_PAGES, anahtar)
    assert deger not in (CIPLAK_ISP | CIPLAK_AKI), (
        '%s = %r hâlâ çıplak' % (anahtar, deger))
    assert '(' in deger or 'Vacuum' in deger or 'Sea' in deger, (
        '%s = %r bir tanım eki taşımalı' % (anahtar, deger))


@pytest.mark.parametrize('anahtar,parca', [
    # Hibrit sayfa sözlüğü: tasarım noktası Isp'si, O/F taraması Isp'si ve
    # referans-cidar akı lejantı tanımlı adlarını korumalı.
    ('adv.pop.isp', 'design point'),
    ('adv.js.ispAxis', 'O/F scan'),
    ('adv.txt.ispImplied', 'implied'),
    ('adv.txt.wallHeatFluxBartz', 'reference cooled wall'),
])
def test_hibrit_sozlugundeki_etiketler_tanimli(anahtar, parca):
    deger = _sozluk_degeri(I18N_ADVANCED, anahtar)
    assert parca in deger, ('%s = %r beklenen tanım ekini (%r) taşımıyor'
                            % (anahtar, deger, parca))
