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
        # V301/K-B: malzeme seçicilerinin seçenekleri sunucudan (Jinja
        # döngüsü, `{{ o.value }}`) gelir; ham şablonda değer yer tutucudur.
        # Tarayıcıda seçili olan sunucunun varsayılanıdır — alan gönderilmez,
        # uç aynı varsayılanı uygular.
        if chosen and '{{' not in chosen.group(1):
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
        # ÖH D18 (P2B4-01): bu alan 'bağımsız ikinci tanık' DEĞİLDİ; aynı
        # eğri için İKİNCİ ve çelişen bir sınıflandırıcıydı (ölçüm: 54
        # koşunun 30'unda thrust_curve_type ile farklı sınıf). Eski kopya
        # söküldü; alan artık thrust_curve_type'ın küçük harfli hâlidir.
        # Bekçi de bunu böyle okur: tanıklık eğri SAYILARINDAN gelir
        # (degisim / tepe_ortalama), etiketten değil.
        'profil': (data.get('grain_design') or {}).get('burn_profile'),
        'sinif': ((data.get('detailed_analysis') or {})
                  .get('thrust_profile_analysis') or {}
                  ).get('thrust_curve_type'),
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


# ---------------------------------------------------------------------------
# T49 — BATES nötrlüğü (V305/C1-t49, 28 Eki 2026; ana model kararı)
#
# Eski bekçi "varsayılan koşu nötr yanar" diyordu. V301/K-A çekirdeği 48 mm'ye,
# V301/K-D (52da83f12, 27 Eki) toplam tane boyunu 500 -> 400 mm'ye indirdi
# (KNDX varsayılanında G0 kütle akısı eşiği; gerekçe hrma/app.py
# SOLID_DEFAULT_GEOMETRY_MM). Varsayılan GERİ ALINMADI (ana model kararı);
# yanlış olan kullanıcıya görünen "varsayılan blokta nötr" metniydi. Bekçi
# üçe ayrıldı:
#   (i)   nötrlük bir GEOMETRİ özelliğidir ve açık nötr geometride sınanır;
#   (ii)  varsayılan tanenin azalan (regressive) olduğu K-D'ye çapalanır;
#   (iii) ipucu, HTML yedeği ve iki kılavuzdaki sayılar ürünün ölçümüyle
#         aynıdır (metin bir daha bayatlarsa kırmızı).
#
# Nötr koşul (dış yüzü kaplı, uçları açık BATES tanesi; D dış, d çekirdek
# çapı, L tane boyu, x yanan web): A(x) = π(d+2x)(L−2x) + (π/2)(D² − (d+2x)²).
# A(0) = πdL + (π/2)(D² − d²), A(w) = πD(L − D + d), w = (D − d)/2;
# A(0) = A(w) ⟺ L = (3D + d)/2 (R. Nakka, "Solid Rocket Motor Theory —
# Grain Design"; kapalı biçim burada türetildi). A(x) x'te içbükey ikinci
# derecedir (A'' = −12π), tepe x* = (L − 2d)/6'da.
# ---------------------------------------------------------------------------
def _t49_kos(client, payload):
    body = client.post('/calculate_solid', json=payload)
    assert body.status_code == 200, body.get_data(as_text=True)[:400]
    data = body.get_json()
    gd = data['grain_design']
    return {
        'ab0': gd['burning_surface_initial_cm2'],
        'ab1': gd['burning_surface_final_cm2'],
        'abmax': data['throat_sizing']['burn_area_ratio_max_over_initial'],
        'kn0': gd['Kn_initial'],
        'kn1': gd['Kn_final'],
        'profil': gd.get('burn_profile'),
        'inhibitor': gd.get('inhibitor_config'),
        'boy': gd.get('grain_length_mm'),
        'tane': gd.get('number_of_segments'),
    }


def _t49_notr_govde(html_text):
    """Sayfa varsayılanı + tane boyu nötr koşulda: L_tane = (3D + d)/2."""
    payload = form_defaults(html_text)
    dis, cek = payload['outer_diameter'], payload['core_diameter']
    adet = int(payload['grain_count'])
    payload['grain_length'] = adet * (3.0 * dis + cek) / 2.0
    return payload, dis, cek, adet


def _t49_alan_mm2(dis, cek, boy, x):
    """Tek tane yanma alanı (dış yüz kaplı, iki uç açık), mm²."""
    import math
    ic = cek + 2.0 * x
    return math.pi * ic * (boy - 2.0 * x) + math.pi / 2.0 * (dis ** 2 - ic ** 2)


def test_t49_bates_notr_kosulunda_notr_yaniyor(html, client):
    """(i) Nötrlük açık geometride: L_tane = (3D + d)/2, uçlar açık.

    Ölçüldü (28 Eki, 100/48 mm, 3 × 174 mm, KNDX): A_b 1149,8 -> 1153,6 cm²
    (+%0,33; son örnek web sonundan hemen önce), A_b,max/A_b,0 1,0827
    (kapalı biçim 1,0832; fark çözücünün web adımı), Kn 222,7 -> 223,4,
    itki tepe/ortalama 1,100. Eşikler eski bekçinin eşikleridir (|ΔA_b| <
    %10, A_b,max/A_b,0 < 1,10, tepe/ortalama < 1,20); gevşetilmedi,
    sınandıkları geometri açık yazıldı.
    """
    payload, dis, cek, adet = _t49_notr_govde(html)
    boy = payload['grain_length'] / adet
    r = _t49_kos(client, payload)
    assert r['tane'] == adet and r['inhibitor'] == 'outer_surface'
    # Başlangıç alanı kapalı biçimle (saf geometri).
    assert r['ab0'] == pytest.approx(
        adet * _t49_alan_mm2(dis, cek, boy, 0.0) / 100.0, rel=1e-9)
    # Nötr koşulun tanımı: web sonundaki alan başlangıçtakine eşit.
    web = (dis - cek) / 2.0
    assert _t49_alan_mm2(dis, cek, boy, web) == pytest.approx(
        _t49_alan_mm2(dis, cek, boy, 0.0), rel=1e-12)
    assert abs(r['ab1'] - r['ab0']) / r['ab0'] < 0.01, (
        'nötr geometride yanma alanı korunmuyor: %.1f -> %.1f cm²'
        % (r['ab0'], r['ab1']))
    assert r['abmax'] < 1.10, ('nötr geometride A_b,max/A_b,0 = %.4f'
                               % r['abmax'])
    # Tepe kapalı biçimin tepesini AŞAMAZ (ayrık örnekleme yalnız altında
    # kalabilir); altında kalma payı web adımıdır (ölçülen 4,4e-4).
    x_tepe = (boy - 2.0 * cek) / 6.0
    assert 0.0 < x_tepe < web
    kapali = (_t49_alan_mm2(dis, cek, boy, x_tepe)
              / _t49_alan_mm2(dis, cek, boy, 0.0))
    assert kapali * (1.0 - 2e-3) <= r['abmax'] <= kapali * (1.0 + 1e-9), (
        r['abmax'], kapali)
    assert abs(r['kn1'] / r['kn0'] - 1.0) < 0.01
    shape = thrust_shape(payload, client)
    assert shape['tepe_ortalama'] < 1.20, shape['tepe_ortalama']
    assert shape['profil'] == (shape['sinif'] or '').lower(), (
        'burn_profile %r ⟷ thrust_curve_type %r — iki alan yine ayrıştı'
        % (shape['profil'], shape['sinif']))


def test_t49_varsayilan_tane_regresif_kd_capasi(html, client):
    """(ii) Varsayılan tane nötr DEĞİL, azalan: K-D 52da83f12 çapası.

    Ölçüldü (28 Eki, sayfa varsayılanları 100/48/400 mm, 3 tane, KNDX,
    uçlar açık + dış kaplı): A_b 965,851245419646 -> 772,3260968968261 cm²
    (−%20,0), Kn 235,0 -> 187,9, burn_profile 'regressive'. Tane boyu
    133,3 mm, nötr koşulun (174 mm) altında. Değer bilerek böyle: K-D varsayılan
    boyu G0 eşiği için indirdi; bu bekçi o kararın SONUCUNU adıyla kilitler.
    """
    payload = form_defaults(html)
    assert payload['grain_length'] == 400.0, (
        'varsayılan tane boyu K-D (52da83f12) çapasından kaydı: %r'
        % payload['grain_length'])
    r = _t49_kos(client, payload)
    assert r['inhibitor'] == 'outer_surface', (
        'inhibitör düzeni BATES değil: %r' % r['inhibitor'])
    dis, cek = payload['outer_diameter'], payload['core_diameter']
    adet = int(payload['grain_count'])
    boy = payload['grain_length'] / adet
    assert boy < (3.0 * dis + cek) / 2.0, 'varsayılan artık nötr boyda'
    assert r['ab0'] == pytest.approx(
        adet * _t49_alan_mm2(dis, cek, boy, 0.0) / 100.0, rel=1e-9)
    assert r['ab0'] == pytest.approx(965.851245419646, rel=1e-9)
    assert r['ab1'] == pytest.approx(772.3260968968261, rel=1e-9)
    assert r['kn1'] / r['kn0'] == pytest.approx(r['ab1'] / r['ab0'],
                                                rel=1e-9)
    assert r['profil'] == 'regressive'


def _t49_bicim(x, dil):
    """Bir ondalık; tam sayı ise ondalıksız (174, 133.3). TR'de virgül."""
    s = '%.1f' % x
    if s.endswith('.0') and abs(x - round(x)) < 1e-9:
        s = s[:-2]
    return s.replace('.', ',') if dil == 'tr' else s


def _t49_yuzde(oran, dil):
    """Bağıl değişim: EN '+8.3%' / '-20.0%', TR '+%8,3' / '-%20,0'."""
    deger = 100.0 * oran
    isaret = '-' if deger < 0 else '+'
    sayi = ('%.1f' % abs(deger))
    if dil == 'tr':
        return '%s%%%s' % (isaret, sayi.replace('.', ','))
    return '%s%s%%' % (isaret, sayi)


def _t49_kn(a, b, dil):
    f = (lambda v: ('%.1f' % v).replace('.', ',')) if dil == 'tr' else (
        lambda v: '%.1f' % v)
    return 'Kn %s -> %s' % (f(a), f(b))


def test_t49_ipucu_sayilari_urun_olcumuyle_ayni(html, client):
    """(iii) İpucu, HTML yedeği ve iki kılavuz ürünün ölçtüğü sayıyı söyler.

    Sayılar burada ÜRÜNDEN ölçülür ve metne biçimlenir; metin bir daha
    bayatlarsa (varsayılan, model ya da metin değişirse) bu bekçi kırmızıdır.
    """
    import html as html_mod
    notr_govde, dis, cek, adet = _t49_notr_govde(html)
    notr = _t49_kos(client, notr_govde)
    vars_govde = form_defaults(html)
    vars_ = _t49_kos(client, vars_govde)
    kapli_govde = dict(vars_govde, inhibit_front=True, inhibit_rear=True)
    kapli = _t49_kos(client, kapli_govde)
    assert kapli['inhibitor'] == 'outer_surface_and_front_face_and_rear_face'
    l_notr = notr_govde['grain_length'] / adet
    l_vars = vars_govde['grain_length'] / adet

    parca = {}
    for dil in ('en', 'tr'):
        b = lambda v: _t49_bicim(v, dil)  # noqa: E731
        y = lambda v: _t49_yuzde(v, dil)  # noqa: E731
        k = lambda a, c: _t49_kn(a, c, dil)  # noqa: E731
        if dil == 'en':
            parca[dil] = [
                'each grain is (3D + d)/2 long',
                'Measured at %s/%s mm, %d × %s mm: %s, peak %s' % (
                    b(dis), b(cek), adet, b(l_notr),
                    k(notr['kn0'], notr['kn1']), y(notr['abmax'] - 1.0)),
                'The default grain (%d × %s mm) is shorter and burns '
                'regressive: %s (%s)' % (
                    adet, b(l_vars), k(vars_['kn0'], vars_['kn1']),
                    y(vars_['kn1'] / vars_['kn0'] - 1.0)),
                '(default grain: %s, peak %s)' % (
                    k(kapli['kn0'], kapli['kn1']), y(kapli['abmax'] - 1.0)),
            ]
        else:
            parca[dil] = [
                'her tane (3D + d)/2 boyunda olduğunda yanma nötrdür',
                '%s/%s mm çaplı, %d × %s mm tanelerle ölçüldü: %s, tepe %s' % (
                    b(dis), b(cek), adet, b(l_notr),
                    k(notr['kn0'], notr['kn1']), y(notr['abmax'] - 1.0)),
                'Varsayılan tane (%d × %s mm) bundan kısadır ve azalan '
                'profille yanar: %s (%s)' % (
                    adet, b(l_vars), k(vars_['kn0'], vars_['kn1']),
                    y(vars_['kn1'] / vars_['kn0'] - 1.0)),
                '(varsayılan tane: %s, tepe %s)' % (
                    k(kapli['kn0'], kapli['kn1']), y(kapli['abmax'] - 1.0)),
            ]

    sayfalar = (REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n_pages.js'
                ).read_text(encoding='utf-8')
    anahtarlar = ('solid.ui.prevents_burning_on_forward_end_face',
                  'solid.ui.prevents_burning_on_aft_end_face')
    metinler = {'en': [], 'tr': []}
    for anahtar in anahtarlar:
        bulunan = re.findall(r"'%s': '([^']*)'" % re.escape(anahtar),
                             sayfalar)
        assert len(bulunan) == 2, (anahtar, len(bulunan))  # EN, TR blokları
        metinler['en'].append(('i18n EN ' + anahtar, bulunan[0]))
        metinler['tr'].append(('i18n TR ' + anahtar, bulunan[1]))
        yedek = re.search(r'data-i18n="%s">([^<]*)</span>'
                          % re.escape(anahtar), html)
        assert yedek, anahtar
        assert html_mod.unescape(yedek.group(1)) == bulunan[0], (
            '%s: HTML yedeği EN metinden ayrıştı' % anahtar)

    def _tex(yol, isaret):
        satirlar = [s for s in (REPO_ROOT / 'docs' / 'user_guide' / yol)
                    .read_text(encoding='utf-8').splitlines() if isaret in s]
        assert len(satirlar) == 2, (yol, len(satirlar))
        return [(yol, s.replace('-\\textgreater{}', '->')
                 .replace('\\%', '%').replace(' -- ', ' — '))
                for s in satirlar]

    metinler['en'] += _tex('HRMA-User-Guide-EN.tex',
                           'In a BATES stack the end faces')
    metinler['tr'] += _tex('HRMA-Kullanma-Kilavuzu-TR.tex',
                           'BATES yığınında uç yüzler')
    for dil in ('en', 'tr'):
        for nerede, metin in metinler[dil]:
            for beklenen in parca[dil]:
                assert beklenen in metin, (
                    '%s: ürün ölçümü metinde yok (bayat sayı?)\n  '
                    'beklenen: %s\n  metin: %s' % (nerede, beklenen, metin))
            assert 'default grain: Kn 160' not in metin
            assert 'varsayılan blokta ölçüldü' not in metin


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
    # ÖH D18 (P2B4-01): tek kaynak burada da sınanır.
    assert shape['profil'] == (shape['sinif'] or '').lower(), (
        'burn_profile %r ⟷ thrust_curve_type %r' % (shape['profil'],
                                                    shape['sinif']))


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
    # v3.0.1 (26 Eki, N-CEA-2): bant motor kaynağında literal değil, katalogla
    # ORTAK sabitten okunur (PROPELLANT_C_STAR_RANGE_M_S; alt sınır 800 → 700,
    # kara barutun NASA CEA c*'ı 784,6-788,7 m/s). Ayna testi o sabitin motorca
    # okunduğunu ve formun aynı iki sayıyı taşıdığını sınar.
    assert re.search(r"_override_val\('char_velocity',\s*\*PROPELLANT_C_STAR_RANGE_M_S\)",
                     source), 'motor c* bandını ortak sabitten okumuyor'
    from hrma.data.propellants_db import PROPELLANT_C_STAR_RANGE_M_S
    alt, ust = (float(x) for x in PROPELLANT_C_STAR_RANGE_M_S)

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
    # numTxt: ürünün GERÇEK sayı biçimleyicisi (D35 sayi-bicimi, 8f9313ca);
    # şablondan kesilir, taklit yazılmaz. window.I18N yok → ürünün geri düşüşü.
    proc = run_node(harness(html, ['numTxt', 'updateCharVelocityBand'], body,
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
    # V301/K-A (KT-06/KT-13; ana model kararı 3) — TERS KAPIYA ÇEVRİLDİ.
    # Bant dışı değer eskiden SESSİZCE yerleşik c*'a dönüyordu (200; iki
    # farklı girdi aynı sonucu veriyordu — bu düğüm o kusuru KİLİTLİYORDU).
    # Artık tasarım yayımlanmaz: 422 input_not_accepted, alan + kabul
    # aralığı adıyla. Bant içi değer eskisi gibi uygulanır.
    payload = form_defaults(html)
    for value in (508.7, 3000.0):
        payload['char_velocity'] = value
        body = client.post('/calculate_solid', json=payload)
        assert body.status_code == 422, body.get_data(as_text=True)[:300]
        j = body.get_json()
        assert j['error_code'] == 'input_not_accepted', j
        kayit = [k for k in j['invalid_fields']
                 if k['field'] == 'char_velocity']
        from hrma.data.propellants_db import PROPELLANT_C_STAR_RANGE_M_S
        assert kayit and kayit[0]['accepted_range'] == [
            float(x) for x in PROPELLANT_C_STAR_RANGE_M_S], j
        assert kayit[0]['submitted'] == pytest.approx(value)
    payload['char_velocity'] = 2400.0
    body = client.post('/calculate_solid', json=payload)
    assert body.status_code == 200, body.get_data(as_text=True)[:300]
    assert body.get_json()['c_star'] > 1518.3 * 1.2, (
        'bant içi 2400 m/s uygulanmıyor')


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

// v3.0.1 (V301/N-grafik G3): bant metni eksen başlığının döndürülmüş
// ikinci satırından çizim alanının sol üstündeki YATAY nota taşındı
// (ölçüm: docs/scofield/raw/OH/V301/grafik/RAPOR.md). Eksen başlığı
// yalın kalır; metin ve sayılar aynı.
// V301/K-C1 (NK-28): matematik gösterimi ("0 ∉ [a … b]  Δ x%") düz
// cümleye çevrildi ("Axis does not start at 0: it shows a – b (span x%)");
// sayılar ve basamaklar AYNI (ölçüm: K-C1/RAPOR.md NK-28).
const bantNotu = ((out.annotations || []).find(
    (a) => String(a.text).indexOf('does not start at 0') >= 0) || {}).text || '';
ok(String(out.yaxis.title) === 'Thrust (N)',
   'eksen başlığına not eklenmiş: ' + out.yaxis.title);
ok(bantNotu.indexOf('it shows 530.41 – 532.66') >= 0,
   'bant ilan edilmiyor: ' + bantNotu);
// D35 sayi-bicimi OH-GT-28 (rapor §5, 8f9313ca): yüzde I18N.percent
// kanonundan; EN'de işaret sayıya BİTİŞİK ve sonra ('0.42%'), TR'de önce
// ('%0,42'). Düzenekte sözlük yok → ürünün geri düşüşü EN biçimi basar.
// Sayının kendisi (2 basamak, 0.4213 → '0.42') DEĞİŞMEDİ.
ok(bantNotu.indexOf('(span 0.42%)') >= 0,
   'göreli genişlik ilan edilmiyor: ' + bantNotu);
const bantKutusu = (out.annotations || []).find(
    (a) => String(a.text).indexOf('does not start at 0') >= 0) || {};
ok(bantKutusu.textangle === undefined || bantKutusu.textangle === 0,
   'bant notu döndürülmüş');

// Aralık hâlâ veri bandına oturuyor (0'a çekilmedi).
ok(out.yaxis.range && out.yaxis.range[0] > 500,
   'y aralığı sıfıra çekilmiş: ' + JSON.stringify(out.yaxis.range));
ok(out.yaxis.rangemode !== 'tozero', "rangemode 'tozero' olmuş");

// Negatif kontrol 1: sıfır zaten bandın içindeyse işaret KONMAZ.
const out2 = hrmaPlotLayout({ yaxis: { title: 'Acceleration (g)' } },
                            [-3.0, 0.0, 12.0]);
ok(String(out2.yaxis.title) === 'Acceleration (g)' && !(out2.annotations || []).length,
   'sıfır bandın içindeyken işaret kondu: ' + out2.yaxis.title);

// Negatif kontrol 2: eksende zaten aralık varsa dokunulmaz.
const out3 = hrmaPlotLayout({ yaxis: { title: 'Thrust (N)', range: [0, 600] } }, y);
ok(String(out3.yaxis.title) === 'Thrust (N)' && !(out3.annotations || []).length,
   'kullanıcı aralığı varken işaret kondu: ' + out3.yaxis.title);

// Büyük bantta yüzde tek ondalıkla yazılır (BATES varsayılanı: 6114 -> 8244).
const out4 = hrmaPlotLayout({ yaxis: { title: 'Thrust (N)' } },
                            [6114.499, 8243.776, 6236.400]);
ok(JSON.stringify(out4.annotations || []).indexOf('(span 25.8%)') >= 0,
   'geniş bant yüzdesi yanlış: ' + JSON.stringify(out4.annotations));
"""
    proc = run_node(
        # numTxt/pctTxt (D35 sayi-bicimi) ve hrmaPlotSeparators (D36
        # onemli2-kati, Plotly TR ondalığı): ürünün çağırdığı GERÇEK
        # yardımcılar; şablondan kesilir, taklit yazılmaz.
        harness(html, ['numTxt', 'pctTxt', 'hrmaAxisRange', 'hrmaSigStr',
                       'hrmaMarkSuppressedZero', 'hrmaPlotSeparators',
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
