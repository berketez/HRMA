"""Faz 6 / F1b — katı motor sayfasının (solid.html) beş bekçisi.

Tarayıcı denetimi 3 Ağustos 2026'da ``/solid`` sayfasında sekiz kusur ölçtü;
beşi bu şablonun içinde kapatıldı, üçü (T66 rıhtım ondalıkları, T67 yörünge
göstergesi, T70 kesitteki segment boşlukları) başka dosyalara düştüğü için
burada YOKTUR — kusurlu davranışı "beklenen" diye kilitlemek yasak.

Kilitlenen kalemler ve ölçülen değerler (önce -> sonra):

* T49 — varsayılan inhibitör düzeni bir BATES grain'i DEĞİLDİ (ön/arka yüz
  kaplı, dış yüzey açık). Aynı sayfanın 'Thrust Curve' yardımı 'BATES
  (neutral)' derken itki 15845 -> 9727 N (-%38,6) düşüyordu. Şablon
  varsayılanı motorun KENDİ varsayılanının tersiydi
  (solid_rocket_engine.py:1413-1415: front=False, rear=False, outer=True).
  Düzeltmeden sonra 6114 -> 6236 N (+%2,0), tepe/ortalama 1,26 -> 1,10.
* T50 — 'Computing trajectory...' satırı iş bittikten sonra da ekrandaydı
  (2., 10. ve 25. saniyede, 9 iz çizilmişken). Plotly 1.58.5 çizim kabını
  ``insert('div', ':first-child')`` ile ekler, kabı temizlemez; paragraf
  grafiğin altında kalıyordu. Ölçüm: p sayısı 1 -> 0 (iz sayısı 9 aynı).
* T51 — c* alanı [800, 2500] m/s dışında SESSİZCE düşüyordu: form 508,7 ve
  form 3000 (5,9 kat) birebir aynı sonucu veriyordu (c* 1518,3 m/s / 12994 N
  / 205,3 s). Alan artık bandı taşıyor (HTML5 geçerliliği 508,7 ve 3000 için
  true -> false) ve teslim edilen c* ekranda gösteriliyor.
* T52 — çift eksenli iki alt grafikte hangi serinin hangi eksene ait olduğu
  okunamıyordu; iki seri neredeyse tam orantılı olduğu için (F/Pc oranı
  152,9-156,3, %2,2 bant) eğriler üst üste düşüp tek çizgi görünüyordu.
  Efsane 'Thrust / Chamber Pressure / Burn Area / Kn' -> 'Thrust ← /
  Chamber Pressure → / Burn Area ← / Kn →', sağ eksen serileri noktalı.
* T69 — uç yanmalı grain'de eğri 532,66 -> 530,41 N (%0,42) iken y ekseni
  tam o bandı kaplıyor, "dik düşüş" gibi okunuyordu ve eksende hiçbir işaret
  yoktu. Eksen başlığı: 'Thrust (N)' -> 'Thrust (N)<br>0 ∉ [530.41 …
  532.66]  Δ 0.42 %'. Eksen aralığı BİLEREK değiştirilmedi (sayfa sözleşmesi
  ``rangemode: 'tozero'`` kullanımını yasaklıyor).
"""

import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SOLID = REPO_ROOT / 'hrma' / 'templates' / 'solid.html'
ENGINE = REPO_ROOT / 'hrma' / 'engines' / 'solid_rocket_engine.py'

needs_node = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')


@pytest.fixture(scope='module')
def html():
    return SOLID.read_text(encoding='utf-8')


@pytest.fixture()
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Şablondan kaynak sökme + node koşum düzeneği
# ---------------------------------------------------------------------------
def js_function(html_text, name):
    """``function name(...) { ... }`` gövdesini şablondan söker.

    Sayfadaki üst düzey fonksiyonlar 8 boşluk girintili; kapanış süslü
    parantezi de öyle. (Aynı kural test_solid_page_contract.py'de de geçerli.)
    """
    start = -1
    for marker in ('\n        function %s(' % name,
                   '\n        async function %s(' % name):
        start = html_text.find(marker)
        if start >= 0:
            break
    assert start >= 0, '%s fonksiyonu solid.html içinde yok' % name
    end = html_text.find('\n        }\n', start)
    assert end > start, '%s fonksiyonunun kapanışı bulunamadı' % name
    return html_text[start + 1:end + len('\n        }')]


#: Asgari DOM taklidi — gerçek tarayıcı yok, amaç SAYISAL/METİNSEL davranışı
#: sabitlemek. (F1a dosyasındaki düzenekten bilerek bağımsız: iki dosya ayrı
#: ajanlarda, çapraz import ikisini birbirine kilitlerdi.)
STUB = r"""
const ELS = {};
function el(id, value) {
    ELS[id] = { id: id, value: String(value), style: {}, textContent: '',
                dataset: {}, validity: { valid: true },
                addEventListener() {} };
    return ELS[id];
}
const document = {
    getElementById(id) {
        return Object.prototype.hasOwnProperty.call(ELS, id) ? ELS[id] : null;
    },
    querySelector() { return null; },
    querySelectorAll() { return []; },
};
const window = {};

const fail = [];
const ok = (cond, msg) => { if (!cond) fail.push(msg); };
const yakin = (a, b, tol, msg) =>
    ok(Math.abs(a - b) <= tol, msg + ' (ölçülen ' + a + ', beklenen ' + b + ')');
function bitir() {
    if (fail.length) { console.log(fail.join('\n')); process.exit(1); }
    console.log('OK');
}
"""


def run_node(source):
    handle = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8')
    handle.write(source)
    handle.close()
    try:
        return subprocess.run(['node', handle.name],
                              capture_output=True, text=True)
    finally:
        os.unlink(handle.name)


def harness(html_text, functions, body, extra=''):
    parts = [STUB, extra]
    parts.extend(js_function(html_text, name) for name in functions)
    parts.append(body)
    parts.append('bitir();')
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Şablonun form varsayılanlarını çözücüye taşıyan yardımcı
# ---------------------------------------------------------------------------
def form_defaults(html_text):
    """solid.html'deki sayı/onay/seçim alanlarının VARSAYILAN değerleri.

    Sayfanın ``collectAllParameters()`` fonksiyonu bu id'leri aynı adla
    gönderdiği için sözlük doğrudan ``/calculate_solid`` gövdesi olarak
    kullanılabilir. Böylece bekçi şablonun gerçek varsayılanını ölçer —
    testin içine ikinci bir varsayılan kopyası yazılmaz.
    """
    out = {}
    for match in re.finditer(r'<input\b([^>]*)>', html_text):
        attrs = match.group(1)
        ident = re.search(r'id="([^"]+)"', attrs)
        if not ident:
            continue
        if 'type="checkbox"' in attrs:
            out[ident.group(1)] = bool(re.search(r'\bchecked\b', attrs))
        elif 'type="number"' in attrs:
            value = re.search(r'value="([^"]*)"', attrs)
            if value and value.group(1) != '':
                try:
                    out[ident.group(1)] = float(value.group(1))
                except ValueError:
                    pass
    for match in re.finditer(r'<select\b([^>]*)>(.*?)</select>', html_text, re.S):
        ident = re.search(r'id="([^"]+)"', match.group(1))
        if not ident:
            continue
        chosen = (re.search(r'<option value="([^"]*)"[^>]*\bselected\b',
                            match.group(2))
                  or re.search(r'<option value="([^"]*)"', match.group(2)))
        if chosen:
            out[ident.group(1)] = chosen.group(1)
    return out


def thrust_shape(payload, client):
    body = client.post('/calculate_solid', json=payload)
    assert body.status_code == 200, body.get_data(as_text=True)[:400]
    data = body.get_json()
    curve = data['thrust_curve']['thrust']
    assert len(curve) > 10, 'itki eğrisi yok'
    mean = sum(curve) / len(curve)
    return {
        'ilk': curve[0],
        'son': curve[-1],
        'degisim': (curve[-1] - curve[0]) / curve[0],
        'tepe_ortalama': max(curve) / mean,
        'ortalama': mean,
        # Çözücünün KENDİ sınıflandırması — eğri şeklinden bağımsız ikinci tanık.
        'profil': (data.get('grain_design') or {}).get('burn_profile'),
        'inhibitor': (data.get('grain_design') or {}).get('inhibitor_config'),
    }


# ---------------------------------------------------------------------------
# T49 — varsayılan inhibitör düzeni gerçekten BATES olmalı
# ---------------------------------------------------------------------------
def test_t49_sablon_varsayilani_motorun_varsayilaniyla_ayni(html):
    """Şablon, motorun kendi inhibitör varsayılanını TERSİNE çeviremez.

    Motor (solid_rocket_engine.py:1413-1415) BATES tanımını uyguluyor:
    uç yüzler açık, dış silindir kaplı. Form bunları koşulsuz gönderdiği
    için varsayılanı ters kurmak motorun tanımını sessizce eziyordu.
    """
    source = ENGINE.read_text(encoding='utf-8')
    motor = {}
    for flag in ('inhibit_front', 'inhibit_rear', 'inhibit_outer'):
        found = re.search(r"_flag_opt\('%s',\s*(True|False)\)" % flag, source)
        assert found, '%s motor varsayılanı okunamadı' % flag
        motor[flag] = (found.group(1) == 'True')

    sablon = form_defaults(html)
    for flag, beklenen in motor.items():
        assert sablon.get(flag) is beklenen, (
            '%s: şablon %r, motor %r — form motorun BATES tanımını eziyor'
            % (flag, sablon.get(flag), beklenen))


def test_t49_varsayilan_bates_notr_yaniyor(html, client):
    """Varsayılan koşu 'BATES (neutral)' iddiasını tutmalı.

    Ölçüm (3 Ağustos 2026, /calculate_solid, şablon varsayılanları):
    6114 -> 6236 N (+%2,0), tepe/ortalama 1,10.
    """
    shape = thrust_shape(form_defaults(html), client)
    assert abs(shape['degisim']) < 0.10, (
        'varsayılan yanma nötr değil: %.0f -> %.0f N (%+.1f%%)'
        % (shape['ilk'], shape['son'], 100 * shape['degisim']))
    assert shape['tepe_ortalama'] < 1.20, (
        'tepe/ortalama %.3f — nötr bir BATES eğrisi için fazla tümsekli'
        % shape['tepe_ortalama'])
    # Çözücünün kendi etiketi de sayfanın iddiasını doğrulamalı.
    assert shape['profil'] == 'neutral', (
        "çözücü varsayılan koşuyu %r diye sınıflandırıyor; sayfa 'BATES "
        "(neutral)' diyor" % shape['profil'])
    assert shape['inhibitor'] == 'outer_surface', (
        'inhibitör düzeni BATES değil: %r' % shape['inhibitor'])


def test_t49_negatif_kontrol_eski_duzen_gerileyici(html, client):
    """Negatif kontrol: eski düzen geri gelirse eğri GERİLEYİCİ olur.

    Bu test yukarıdaki nötrlük iddiasının boş olmadığını kanıtlar — aynı
    gövdeyle yalnız üç onay kutusu ters çevrilince ölçüm -%38,6'ya düşer.
    """
    payload = form_defaults(html)
    payload.update(inhibit_front=True, inhibit_rear=True, inhibit_outer=False)
    shape = thrust_shape(payload, client)
    assert shape['degisim'] < -0.25, (
        'eski düzen artık gerileyici değil; bu testin çapası kaymış: %+.1f%%'
        % (100 * shape['degisim']))
    assert shape['profil'] == 'regressive', (
        'eski düzenin çözücü etiketi %r (beklenen regressive)' % shape['profil'])


# ---------------------------------------------------------------------------
# T50 — 'Computing trajectory...' satırı çizimden önce silinmeli
# ---------------------------------------------------------------------------
def test_t50_durum_satiri_cizimden_once_siliniyor(html):
    """Kap, Plotly çağrısından ÖNCE temizlenmeli.

    Plotly 1.58.5 kabı temizlemez (çizim kabını ':first-child' olarak
    EKLER), bu yüzden durum paragrafı grafiğin altında kalıyordu. Ölçüm:
    hesap 0,2 s sürerken metin 25. saniyede hâlâ ekrandaydı.
    """
    body = js_function(html, 'computeTrajectory')
    durum = body.find("solid.js.computing_trajectory")
    temizle = body.find("div.innerHTML = '';")
    cizim = body.find('Plotly.newPlot(div')
    assert durum >= 0, 'durum satırı kayboldu — test çapası geçersiz'
    assert cizim >= 0, 'Plotly.newPlot(div ...) çağrısı bulunamadı'
    assert temizle >= 0, (
        "computeTrajectory kabı temizlemiyor; 'Computing trajectory...' "
        'paragrafı grafiğin altında kalır')
    assert durum < temizle < cizim, (
        'temizleme yanlış yerde: durum=%d temizle=%d çizim=%d'
        % (durum, temizle, cizim))


# ---------------------------------------------------------------------------
# T51 — c* kabul bandı görünür olmalı
# ---------------------------------------------------------------------------
def test_t51_alan_bandi_motorun_bandiyla_ayni(html):
    """HTML5 min/max, motorun kabul aralığının aynası olmalı."""
    source = ENGINE.read_text(encoding='utf-8')
    band = re.search(r"_override_val\('char_velocity',\s*([\d.]+),\s*([\d.]+)\)",
                     source)
    assert band, 'motorun c* bandı okunamadı'
    alt, ust = float(band.group(1)), float(band.group(2))

    tag = re.search(r'<input[^>]*id="char_velocity"[^>]*>', html)
    assert tag, '#char_velocity alanı yok'
    attrs = tag.group(0)
    min_attr = re.search(r'min="([\d.]+)"', attrs)
    max_attr = re.search(r'max="([\d.]+)"', attrs)
    assert min_attr and max_attr, (
        '#char_velocity bandı taşımıyor; bant dışı değer sessizce düşer')
    assert float(min_attr.group(1)) == alt
    assert float(max_attr.group(1)) == ust

    # Aynı iki sayı JS tarafında da tek kaynaktan gelmeli.
    js_min = re.search(r'var CSTAR_MIN_MS = ([\d.]+);', html)
    js_max = re.search(r'var CSTAR_MAX_MS = ([\d.]+);', html)
    assert js_min and js_max, 'c* bant sabitleri JS tarafında yok'
    assert float(js_min.group(1)) == alt
    assert float(js_max.group(1)) == ust


@needs_node
def test_t51_bant_ipucu_disaridaki_degeri_soyluyor(html):
    """Bant dışı girdi kırmızı ve '∉' ile işaretlenir; teslim edilen c* yazılır."""
    body = r"""
el('char_velocity', 1550);
el('char_velocity_band', '');
const NOT = ELS['char_velocity_band'];

updateCharVelocityBand(null);
ok(NOT.textContent.indexOf('≤') >= 0, 'bant ipucu yok: ' + NOT.textContent);
ok(NOT.textContent.indexOf('∉') < 0, 'bant içi değer dışarıda gösterildi');
ok(NOT.style.color === '#7d97a5', 'bant içi değer uyarı rengiyle: ' + NOT.style.color);

updateCharVelocityBand({ c_star: 1472.5 });
ok(NOT.textContent.indexOf('1550.0 → 1472.5 m/s') >= 0,
   'teslim edilen c* gösterilmiyor: ' + NOT.textContent);

ELS['char_velocity'].value = '3000';
updateCharVelocityBand({ c_star: 1518.29 });
ok(NOT.textContent.indexOf('∉') >= 0, 'bant dışı değer işaretlenmedi: ' + NOT.textContent);
ok(NOT.textContent.indexOf('3000.0 → 1518.3 m/s') >= 0,
   'düşen değerin sonucu gösterilmiyor: ' + NOT.textContent);
ok(NOT.style.color === '#ff7a85', 'bant dışı değer uyarı rengi almadı: ' + NOT.style.color);

ELS['char_velocity'].value = '508.7';
updateCharVelocityBand({ c_star: 1518.29 });
ok(NOT.textContent.indexOf('508.7 ∉') >= 0, 'alt bant dışı işaretlenmedi: ' + NOT.textContent);

ELS['char_velocity'].value = '2400';
updateCharVelocityBand({ c_star: 2280.0 });
ok(NOT.textContent.indexOf('∉') < 0, 'bant içi 2400 dışarıda sayıldı: ' + NOT.textContent);
"""
    # Bant sabitleri de ŞABLONDAN sökülür — testin içinde ikinci bir kopya
    # tutmak, sabit değişince bekçinin eski değeri onaylamasına yol açardı.
    sabitler = re.findall(r'var CSTAR_(?:MIN|MAX)_MS = [\d.]+;', html)
    assert len(sabitler) == 2, 'c* bant sabitleri şablondan sökülemedi'
    proc = run_node(harness(html, ['updateCharVelocityBand'], body,
                            extra='\n'.join(sabitler)))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_t51_ipucu_alani_ve_kablolamasi_yerinde(html):
    """İpucu kabı sayfada olmalı ve hesaptan sonra tazelenmeli.

    (Fonksiyonun kendisi doğru çalışsa bile çağrılmıyorsa kullanıcı hiçbir
    şey görmez — bu bekçi tam olarak o boşluğu kapatır.)
    """
    assert 'id="char_velocity_band"' in html, 'bant ipucu kabı yok'
    sonuc = js_function(html, 'displayResults')
    assert 'updateCharVelocityBand(results)' in sonuc, (
        'hesap sonrası bant ipucu tazelenmiyor')
    assert re.search(r"onclick=\"calculateCharVelocity\(\);\s*"
                     r"updateCharVelocityBand\(", html), (
        "'Calculate' düğmesi c* yazdıktan sonra ipucunu tazelemiyor")


def test_t51_cozucu_bant_disini_gercekten_dusuruyor(html, client):
    """Uyarının GEREKÇESİ: bant dışı iki farklı değer aynı sonucu verir.

    Ölçüm (3 Ağustos 2026): form 508,7 ve form 3000 (5,9 kat) -> c* 1518,3
    m/s; form 2400 -> 2280,0 m/s (uygulanıyor). Bu test bandın gerçek
    olduğunu kanıtlar; band değişirse yukarıdaki ayna testi de kırılır.
    """
    payload = form_defaults(html)
    sonuc = {}
    for value in (508.7, 3000.0, 2400.0):
        payload['char_velocity'] = value
        body = client.post('/calculate_solid', json=payload)
        assert body.status_code == 200, body.get_data(as_text=True)[:300]
        sonuc[value] = body.get_json()['c_star']
    assert sonuc[508.7] == pytest.approx(sonuc[3000.0], rel=1e-9), (
        'bant dışı iki değer artık farklı sonuç veriyor: %r' % sonuc)
    assert sonuc[2400.0] > sonuc[3000.0] * 1.2, (
        'bant içi 2400 m/s uygulanmıyor: %r' % sonuc)


# ---------------------------------------------------------------------------
# T52 — çift eksenli serilerde eksen kimliği
# ---------------------------------------------------------------------------
@needs_node
def test_t52_cift_eksenli_seriler_eksenine_baglaniyor(html):
    """Sağ eksen serisi noktalı ve '→', sol eksen serisi '←' almalı.

    Figür sunucudan geliyor; burada yalnız SUNUM düzeltilir. Tek eksenli
    alt grafiklerin izleri (çubuklar) DOKUNULMADAN kalmalı — negatif kontrol.
    """
    body = r"""
const fig = {
  data: [
    { name: 'Propellant Mass Flow', yaxis: 'y',  showlegend: false },
    { name: 'Pressure Distribution', yaxis: 'y2', showlegend: false },
    { name: 'Thrust',           yaxis: 'y3', line: { color: '#00e5ff', width: 3 } },
    { name: 'Chamber Pressure', yaxis: 'y4', line: { color: '#d1495b', width: 2 } },
    { name: 'Burn Area',        yaxis: 'y5', line: { color: '#c792ea', width: 3 } },
    { name: 'Kn',               yaxis: 'y6', line: { color: '#f6c667', width: 2 } }
  ],
  layout: {
    yaxis: {}, yaxis2: {}, yaxis3: {},
    yaxis4: { side: 'right', overlaying: 'y3' },
    yaxis5: {},
    yaxis6: { side: 'right', overlaying: 'y5' }
  }
};
const n = markDualAxisSeries(fig);
ok(n === 4, 'işaretlenen iz sayısı 4 değil: ' + n);
ok(fig.data[2].name === 'Thrust ←', 'sol eksen işareti yok: ' + fig.data[2].name);
ok(fig.data[3].name === 'Chamber Pressure →', 'sağ eksen işareti yok: ' + fig.data[3].name);
ok(fig.data[4].name === 'Burn Area ←', 'sol eksen işareti yok: ' + fig.data[4].name);
ok(fig.data[5].name === 'Kn →', 'sağ eksen işareti yok: ' + fig.data[5].name);
ok(fig.data[3].line.dash === 'dot', 'sağ eksen serisi ayrışmıyor (dash yok)');
ok(fig.data[5].line.dash === 'dot', 'sağ eksen serisi ayrışmıyor (dash yok)');
ok(fig.data[2].line.dash === undefined, 'sol eksen serisi noktalanmış');
ok(fig.data[2].line.color === '#00e5ff', 'renk değiştirilmiş');

// Negatif kontrol: tek eksenli alt grafiğin izleri hiç dokunulmadan kalmalı.
ok(fig.data[0].name === 'Propellant Mass Flow', 'çubuk izi işaretlendi');
ok(fig.data[1].name === 'Pressure Distribution', 'çubuk izi işaretlendi');

// Negatif kontrol: hiç çift eksen yoksa hiçbir iz işaretlenmez.
const tek = { data: [{ name: 'Regression', yaxis: 'y' }], layout: { yaxis: {} } };
ok(markDualAxisSeries(tek) === 0, 'tek eksenli figürde iz işaretlendi');
ok(tek.data[0].name === 'Regression', 'tek eksenli figürün adı değişti');
"""
    proc = run_node(harness(html, ['markDualAxisSeries'], body))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_t52_isaretleme_cizimden_once_cagriliyor(html):
    """İşaretleme Plotly çağrısından ÖNCE yapılmalı; sonra yapılsa etkisiz."""
    body = js_function(html, 'renderSolidPerformance')
    isaret = body.find('markDualAxisSeries(fig)')
    cizim = body.find("Plotly.newPlot('solid_performance_plots'")
    assert cizim >= 0, 'performans panosu çizimi bulunamadı'
    assert isaret >= 0, (
        'çift eksenli seriler işaretlenmiyor; efsane hangi serinin hangi '
        'eksene ait olduğunu söylemiyor')
    assert isaret < cizim, 'işaretleme çizimden sonra yapılıyor (etkisiz)'


# ---------------------------------------------------------------------------
# T69 — bastırılmış sıfır eksende ilan edilmeli
# ---------------------------------------------------------------------------
@needs_node
def test_t69_bastirilmis_sifir_eksende_ilan_ediliyor(html):
    """Uç yanmalı eğride eksen başlığı bandı ve göreli genişliği söylemeli.

    Ölçülen eğri: 532,6566982197179 -> 530,4127596910364 N (%0,42).
    Eksen aralığı BİLEREK veri bandında kalır (sayfa sözleşmesi
    ``rangemode: 'tozero'`` yasağı) — değişen tek şey işaretlemedir.
    """
    body = r"""
const y = [532.6566982197179, 531.5, 530.4127596910364];
const out = hrmaPlotLayout({
    title: 'Thrust vs Time',
    xaxis: { title: 'Time (s)' },
    yaxis: { title: 'Thrust (N)' },
    showlegend: false
}, y);

ok(String(out.yaxis.title).indexOf('Thrust (N)') === 0,
   'eksen başlığı kayboldu: ' + out.yaxis.title);
ok(String(out.yaxis.title).indexOf('0 ∉ [530.41 … 532.66]') >= 0,
   'bant ilan edilmiyor: ' + out.yaxis.title);
ok(String(out.yaxis.title).indexOf('Δ 0.42 %') >= 0,
   'göreli genişlik ilan edilmiyor: ' + out.yaxis.title);

// Aralık hâlâ veri bandına oturuyor (0'a çekilmedi).
ok(out.yaxis.range && out.yaxis.range[0] > 500,
   'y aralığı sıfıra çekilmiş: ' + JSON.stringify(out.yaxis.range));
ok(out.yaxis.rangemode !== 'tozero', "rangemode 'tozero' olmuş");

// Negatif kontrol 1: sıfır zaten bandın içindeyse işaret KONMAZ.
const out2 = hrmaPlotLayout({ yaxis: { title: 'Acceleration (g)' } },
                            [-3.0, 0.0, 12.0]);
ok(String(out2.yaxis.title) === 'Acceleration (g)',
   'sıfır bandın içindeyken işaret kondu: ' + out2.yaxis.title);

// Negatif kontrol 2: eksende zaten aralık varsa dokunulmaz.
const out3 = hrmaPlotLayout({ yaxis: { title: 'Thrust (N)', range: [0, 600] } }, y);
ok(String(out3.yaxis.title) === 'Thrust (N)',
   'kullanıcı aralığı varken işaret kondu: ' + out3.yaxis.title);

// Büyük bantta yüzde tek ondalıkla yazılır (BATES varsayılanı: 6114 -> 8244).
const out4 = hrmaPlotLayout({ yaxis: { title: 'Thrust (N)' } },
                            [6114.499, 8243.776, 6236.400]);
ok(String(out4.yaxis.title).indexOf('Δ 25.8 %') >= 0,
   'geniş bant yüzdesi yanlış: ' + out4.yaxis.title);
"""
    proc = run_node(
        harness(html, ['hrmaAxisRange', 'hrmaSigStr', 'hrmaMarkSuppressedZero',
                       'hrmaPlotLayout'], body,
                extra='var HRMA_PLOT_Y_PAD_FRACTION = 0.08;'))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_t69_isaretleme_gercekten_cagriliyor(html):
    """hrmaPlotLayout, aralığı kendisi kurduğunda işaretlemeyi çağırmalı."""
    body = js_function(html, 'hrmaPlotLayout')
    assert 'hrmaMarkSuppressedZero(out.yaxis, yValues)' in body, (
        'aralık kuruluyor ama bastırılmış sıfır ilan edilmiyor')
    # Eksen aralığı hâlâ veriye oturuyor olmalı — sayfa sözleşmesi gereği.
    assert "rangemode: 'tozero'" not in body
