"""UI · OpenRocket köşesi (Berke §28-11, 5 Eki 2026; 7 Eki 2026) bekçileri.

İstek (aynen): "bu program için openrocket kısmı yanda küçük bir tuşla
açılacak hale gelsin ... biz openrocket i de destekliyoruz mantığı ile olsun".

Ürün: ``hrma/static/js/openrocket_kose.js`` + ``hrma/static/css/
openrocket_kose.css``; üç motor sayfası (sıvı ``/liquid``, katı ``/solid``,
hibrit ``/hybrid``) bu iki dosyayı dahil eder. Sağ kenarda bir sekme, açılınca
yan panel; panelde YALNIZ sayfada zaten çalışan ve testli yetenekler:

* .eng dışa aktarımı: sayfanın kendi düğmesine vekâlet (sıvı/katı
  ``/api/export-eng``, hibrit ``/api/export-openrocket``); eski düğme
  gizlenir, kimliği ve ``onclick``'i DOM'da kalır.
* .ork içe aktarma: 6-DOF panelindeki kutu (``#sd_ork_file``) köşeye
  TAŞINIR; olay dinleyicileri ve kimlikler aynı kalır.
* .eng/.rse içe aktarma (``/api/import/motor-file``): 6-DOF itki kaynağı ve
  doğrulama paneli girdisi olarak YERİNDE kalır; köşe yalnız oraya götürür.

Katmanlar:
  1. Şablon / uç / sözlük: statik, her ortamda koşar.
  2. Karar işlevi (``engDurumu``): node altında GERÇEKTEN koşturulur.
  3. Tarayıcı: gerçek sunucu + gerçek Chromium. Tarayıcı açılamazsa kayıtlı
     tarayıcı ölçümü (``olcum_tarayici.json``) kanıt kapısından okunur ve aynı
     hükümler ona uygulanır; docs'suz ağaçta "kanıt yok" atlaması olur.
  4. Uyumluluk: kurulu OpenRocket'in (``/Applications/OpenRocket.app``) kendi
     RASP yükleyicisi dışa aktarılan .eng'i okumalı; OpenRocket ile gelen
     örnek .ork tasarımlarının içe aktarılan sayısı köşedeki sabitle (OLCUM)
     eşleşmeli. OpenRocket yoksa kayıtlı ölçüm (``olcum_uyumluluk.json``)
     kanıt kapısından okunur.

Ters mutasyon kanıtı: ``docs/scofield/raw/OH/UI/openrocket-kose/rapor.md``.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import plistlib
import re
import shutil
import subprocess
import sys
import time
import zipfile

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from tests.support.kanit import kanit_gerekli  # noqa: E402

JS = KOK / 'hrma' / 'static' / 'js' / 'openrocket_kose.js'
CSS = KOK / 'hrma' / 'static' / 'css' / 'openrocket_kose.css'
I18N_COMMON = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'
SABLONLAR = KOK / 'hrma' / 'templates'
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'UI' / 'openrocket-kose'
TARAYICI_KANIT = KANIT / 'olcum_tarayici.json'
UYUMLULUK_KANIT = KANIT / 'olcum_uyumluluk.json'

OR_APP = pathlib.Path('/Applications/OpenRocket.app')
OR_JAR_DIZINI = OR_APP / 'Contents' / 'Resources' / 'app' / 'jar'
OR_JRE = OR_APP / 'Contents' / 'Resources' / 'jre.bundle' / 'Contents' / 'Home' / 'bin' / 'java'

NODE = shutil.which('node')

#: Sayfa yolu -> (şablon, sayfanın kendi .eng düğmesi seçicisi, beklenen uç)
KOSE_SAYFALARI = {
    '/liquid': ('liquid.html', 'button[onclick="downloadLiquidEng()"]',
                '/api/export-eng', 'downloadLiquidEng'),
    '/solid': ('solid.html', 'button[onclick="downloadSolidEng()"]',
               '/api/export-eng', 'downloadSolidEng'),
    '/hybrid': ('advanced.html', '#downloadEngBtn',
                '/api/export-openrocket', 'downloadEngFile'),
}

BLOK_BAS = '// UI openrocket-kose +k ↓'
BLOK_SON = '// UI openrocket-kose +k ↑'
EM_DASH = '—'
EMOJI = re.compile('[\U0001F000-\U0001FAFF\U00002600-\U000027BF]')


def _oku(yol):
    return pathlib.Path(yol).read_text(encoding='utf-8')


def _js_nesnesi(ad):
    """openrocket_kose.js içindeki ``var AD = { ... };`` düz nesnesini sözlüğe çevirir."""
    kaynak = _oku(JS)
    m = re.search(r'var %s = \{(.*?)\n    \};' % ad, kaynak, re.S)
    assert m, '%s nesnesi openrocket_kose.js içinde bulunamadı' % ad
    sonuc = {}
    for anahtar, deger in re.findall(r"^\s*(\w+):\s*([^,\n]+?),?\s*$", m.group(1), re.M):
        deger = deger.strip()
        if deger.startswith("'"):
            sonuc[anahtar] = deger.strip("'")
        elif deger in ('true', 'false'):
            sonuc[anahtar] = deger == 'true'
        else:
            sonuc[anahtar] = int(deger)
    return sonuc


def _sozluk_bloklari():
    """i18n_common.js'teki köşe bloğu: (EN çiftleri, TR çiftleri)."""
    kaynak = _oku(I18N_COMMON)
    bloklar = []
    i = 0
    while True:
        a = kaynak.find(BLOK_BAS, i)
        if a < 0:
            break
        b = kaynak.find(BLOK_SON, a)
        assert b > a, 'köşe bloğunun kapanış çapası yok'
        govde = kaynak[a + len(BLOK_BAS):b]
        ciftler = re.findall(r"^\s*'(openrocket\.kose\.[\w.]+)':\s*'((?:[^'\\]|\\.)*)',\s*$",
                             govde, re.M)
        bloklar.append([(k, v.replace("\\'", "'").replace('\\"', '"')) for k, v in ciftler])
        i = b + 1
    assert len(bloklar) == 2, 'köşe bloğu EN ve TR sözlüklerinde birer kez olmalı (bulunan %d)' % len(bloklar)
    return bloklar[0], bloklar[1]


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


# ---------------------------------------------------------------------------
# 1. Şablonlar, uçlar, sözlük
# ---------------------------------------------------------------------------

class TestSablonVeUc:
    @pytest.mark.parametrize('yol', sorted(KOSE_SAYFALARI))
    def test_sayfa_koseyi_bir_kez_dahil_eder(self, istemci, yol):
        r = istemci.get(yol)
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert html.count('href="/static/css/openrocket_kose.css"') == 1, yol
        assert html.count('src="/static/js/openrocket_kose.js"') == 1, yol
        # .ork kutusu 6-DOF panelinden taşındığı için betik onun ARDINDA.
        assert html.index('src="/static/js/sixdof_panel.js"') < html.index(
            'src="/static/js/openrocket_kose.js"'), yol

    @pytest.mark.parametrize('yol', sorted(KOSE_SAYFALARI))
    def test_eski_dugme_kimligi_korunur(self, yol):
        sablon, secici, _, islev = KOSE_SAYFALARI[yol]
        html = _oku(SABLONLAR / sablon)
        if secici.startswith('#'):
            assert html.count('id="%s"' % secici[1:]) == 1
        else:
            assert html.count('onclick="%s()"' % islev) == 1
        assert html.count('async function %s()' % islev) == 1, islev

    def test_her_eylemin_ucu_app_te_kayitli(self, istemci):
        from hrma.app import app
        kurallar = {}
        for kural in app.url_map.iter_rules():
            kurallar.setdefault(kural.rule, set()).update(kural.methods or ())
        uclar = _js_nesnesi('UCLAR')
        assert set(uclar) == {'sivi', 'kati', 'hibrit', 'ork', 'motorDosyasi'}
        for ad, uc in uclar.items():
            assert uc in kurallar, '%s ucu (%s) app.url_map içinde yok' % (ad, uc)
            assert 'POST' in kurallar[uc], '%s ucu POST kabul etmiyor' % uc
        for yol, (_, _, uc, _) in KOSE_SAYFALARI.items():
            tur = {'/liquid': 'sivi', '/solid': 'kati', '/hybrid': 'hibrit'}[yol]
            assert uclar[tur] == uc

    @pytest.mark.parametrize('yol', sorted(KOSE_SAYFALARI))
    def test_sayfa_islevi_ayni_ucu_cagirir(self, yol):
        """Vekâlet edilen sayfa işlevi köşenin beyan ettiği uca gider."""
        sablon, _, uc, islev = KOSE_SAYFALARI[yol]
        html = _oku(SABLONLAR / sablon)
        i = html.index('async function %s()' % islev)
        govde = html[i:i + 6000]
        assert "fetch('%s'" % uc in govde, '%s: %s %s çağırmıyor' % (yol, islev, uc)

    def test_gizleme_kurali_yalniz_kose_hazirken(self):
        css = _oku(CSS)
        assert re.search(r'body\.or-kose-hazir\s+\.or-kose-tasindi\s*\{\s*display:\s*none\s*!important;',
                         css), 'gizleme kuralı köşe kurulumuna bağlı değil'
        js = _oku(JS)
        # Sınıf, köşe kurulduktan SONRA eklenir (kurulum başarısızsa düğmeler yerinde kalır).
        assert js.index("classList.add('or-kose-hazir')") > js.index('function kur()')


class TestSozluk:
    def test_en_tr_anahtar_esitligi_ve_dolu_degerler(self):
        en, tr = _sozluk_bloklari()
        assert [k for k, _ in en] == [k for k, _ in tr]
        assert len(en) >= 20
        for (k, ve), (_, vt) in zip(en, tr):
            assert ve.strip() and vt.strip(), k
            assert ve != vt, '%s çevrilmemiş' % k
            assert sorted(re.findall(r'\{(\w+)\}', ve)) == sorted(re.findall(r'\{(\w+)\}', vt)), k

    def test_kodda_kullanilan_anahtarlar_sozlukte_ve_tersi(self):
        en, _ = _sozluk_bloklari()
        tanimli = {k for k, _ in en}
        kullanilan = set(re.findall(r"\bTF?\('(openrocket\.kose\.[\w.]+)'", _oku(JS)))
        assert kullanilan == tanimli, (sorted(kullanilan - tanimli), sorted(tanimli - kullanilan))

    def test_emoji_ve_uzun_tire_yok(self):
        en, tr = _sozluk_bloklari()
        for k, v in en + tr:
            assert EM_DASH not in v and not EMOJI.search(v), k
        for yol in (JS, CSS):
            metin = _oku(yol)
            assert EM_DASH not in metin, yol.name
            assert not EMOJI.search(metin), yol.name

    def test_giris_cumlesi_yalniz_gercek_yonleri_soyler(self):
        """Denetim Ş3: HRMA .ork YAZMAZ; giriş cümlesi okunan (.ork) ve
        yazılan (.eng) biçimi adıyla söyler, EN ve TR aynı içerik."""
        en, tr = (dict(b) for b in _sozluk_bloklari())
        assert en['openrocket.kose.intro'].startswith(
            'HRMA reads OpenRocket designs (.ork) and writes RASP motor files (.eng) '
            'that OpenRocket loads.'), en['openrocket.kose.intro']
        assert tr['openrocket.kose.intro'].startswith(
            "HRMA, OpenRocket tasarımlarını (.ork) okur ve OpenRocket'in yüklediği RASP "
            'motor dosyalarını (.eng) yazar.'), tr['openrocket.kose.intro']
        for d in (en, tr):
            assert d['openrocket.kose.intro'].count('.ork') == 1
            assert d['openrocket.kose.intro'].count('.eng') == 1

    def test_turkce_metinler_turkce_karakterli(self):
        _, tr = _sozluk_bloklari()
        d = dict(tr)
        assert d['openrocket.kose.reason.noMotor'] == 'Önce motoru hesaplayın.'
        assert d['openrocket.kose.title'] == 'OpenRocket dosya alışverişi'
        hepsi = ''.join(d.values())
        for harf in 'çğıöşüİ':
            assert harf in hepsi, harf
        en, _ = _sozluk_bloklari()
        assert not re.search('[çğıİöşüÇĞÖŞÜ]', ''.join(v for _, v in en))


# ---------------------------------------------------------------------------
# 2. Karar işlevi (node altında gerçek dosya)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
class TestKararIslevi:
    KARAR_VAKALARI = [
        # (ad, sayfa, sonuc, asil_devre_disi, etkin, neden, uyari_alanlari)
        ('sonuc_yok_sivi', 'sivi', None, False, False, 'openrocket.kose.reason.noMotor', None),
        ('sonuc_yok_kati', 'kati', None, False, False, 'openrocket.kose.reason.noMotor', None),
        ('sonuc_yok_hibrit', 'hibrit', None, True, False, 'openrocket.kose.reason.noMotor', None),
        ('hibrit_motorsuz_sonuc', 'hibrit', {'performance': {}}, False, False,
         'openrocket.kose.reason.noMotor', None),
        ('hibrit_asil_kapali', 'hibrit', {'motor': {}}, True, False,
         'openrocket.kose.reason.noMotor', None),
        ('hibrit_hazir', 'hibrit', {'motor': {}}, False, True, None, None),
        ('sivi_hazir', 'sivi', {'thrust': 1}, False, True, None, None),
        ('kati_hazir', 'kati', {'thrust': 1}, False, True, None, None),
        ('sivi_eng_kapisi', 'sivi',
         {'openrocket': {'eng_error': {'missing_fields': ['burn_time', 'total_impulse']}}},
         False, True, None, ['burn_time', 'total_impulse']),
        # Devir D4: zarf uyarısı KODU taşınır (metni değil); kodsuz kayıt
        # susturulmaz, kod None olarak gelir ve köşe "tanınmayan" der.
        ('sivi_zarf_kodu', 'sivi',
         {'openrocket': {'eng_envelope_warning': {'error': 'propellant_outside_envelope',
                                                  'message': 'x'}}},
         False, True, None, None, {'kod': 'propellant_outside_envelope'}),
        ('kati_zarf_kodsuz', 'kati',
         {'openrocket': {'eng_envelope_warning': {'message': 'x'}}},
         False, True, None, None, {'kod': None}),
        ('motorsuz_zarf_yok', 'kati', None, False, False,
         'openrocket.kose.reason.noMotor', None, None),
    ]

    def test_eng_durumu(self):
        # Betik stdin ile verilir (test_node_cagri_sozlesmesi: argv ile betik yasak).
        betik = (
            "require(%s);\n"
            "const K = globalThis.HRMAOpenRocketKose;\n"
            "const vakalar = %s;\n"
            "const out = vakalar.map(v => K.engDurumu(v[1], v[2], v[3]));\n"
            "process.stdout.write(JSON.stringify(out));\n"
            % (json.dumps(str(JS)), json.dumps(self.KARAR_VAKALARI)))
        proc = subprocess.run([NODE], input=betik, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        cikti = json.loads(proc.stdout)
        for vaka, d in zip(self.KARAR_VAKALARI, cikti):
            ad, _, _, _, etkin, neden, alanlar = vaka[:7]
            zarf = vaka[7] if len(vaka) > 7 else None
            assert d['zarf'] == zarf, ad
            assert d['etkin'] is etkin, ad
            assert d['neden'] == neden, ad
            if alanlar is None:
                assert d['uyari'] is None, ad
            else:
                assert d['uyari'] == {'alanlar': alanlar}, ad


# ---------------------------------------------------------------------------
# 3. Tarayıcı: gerçek sunucu + gerçek Chromium
# ---------------------------------------------------------------------------

OLC_JS = r'''() => {
  const vis = n => !!(n && n.getClientRects().length && getComputedStyle(n).visibility !== 'hidden');
  const panel = document.getElementById('orKosePanel');
  const sekme = document.getElementById('orKoseSekme');
  const disari = [];
  document.querySelectorAll('button, input[type=file], a').forEach(n => {
    if (n === sekme || (panel && panel.contains(n)) || !vis(n)) return;
    const t = (n.textContent || '') + ' ' + (n.getAttribute('onclick') || '') + ' '
      + (n.getAttribute('accept') || '') + ' ' + (n.id || '');
    if (/openrocket|\.ork|downloadLiquidEng|downloadSolidEng|downloadEngFile|downloadEngBtn/i.test(t))
      disari.push(t.trim().slice(0, 120));
  });
  const eng = document.getElementById('orKoseEngDugme');
  const neden = document.getElementById('orKoseEngNeden');
  const uyari = document.getElementById('orKoseEngUyari');
  const ork = document.getElementById('sd_ork_file');
  // Sayfanın kendi .eng düğmesi: hesaptan önce kabı da gizli olabilir
  // (ölçüldü), bu yüzden gizlemenin KENDİSİ öğe düzeyinde ölçülür.
  const eski = document.querySelector('#downloadEngBtn, button[onclick="downloadLiquidEng()"],'
    + ' button[onclick="downloadSolidEng()"]');
  const dog = document.getElementById('orKoseDogrulamaGoster');
  const dogNeden = document.getElementById('orKoseDogrulamaNeden');
  // Sıvı sayfası: dışa aktarım panelindeki .eng açıklama satırı (li).
  const engTanim = document.querySelector('[data-i18n="liq.ui.openrocket_eng"]');
  const engLi = engTanim && engTanim.closest ? engTanim.closest('li') : null;
  const zarf = document.getElementById('orKoseEngZarf');
  return {
    baslik: (document.getElementById('orKoseBaslik') || {}).textContent || null,
    dog_disabled: dog ? dog.disabled : null,
    dog_neden: dogNeden && !dogNeden.hidden ? dogNeden.textContent : null,
    eng_li_var: !!engLi,
    eng_li_display: engLi ? getComputedStyle(engLi).display : null,
    eng_zarf: zarf && !zarf.hidden ? zarf.textContent : null,
    eng_zarf_kod: zarf && !zarf.hidden ? zarf.getAttribute('data-kod') : null,
    eski_dugme_var: !!eski,
    eski_dugme_display: eski ? getComputedStyle(eski).display : null,
    eski_kap_gorunur: !!(eski && eski.parentElement && vis(eski.parentElement)),
    kuruldu: !!(window.HRMAOpenRocketKose && window.HRMAOpenRocketKose.kuruldu()),
    sekme_gorunur: vis(sekme),
    panel_gorunur: vis(panel),
    eng_disabled: eng ? eng.disabled : null,
    eng_neden: neden && !neden.hidden ? neden.textContent : null,
    eng_uyari: uyari && !uyari.hidden ? uyari.textContent : null,
    eng_uc: document.getElementById('orKoseEng') ? document.getElementById('orKoseEng').getAttribute('data-uc') : null,
    ork_kosede: !!(ork && panel && panel.contains(ork)),
    disarida_gorunur_or: disari,
    // Köşenin yatay taşmaya KATKISI: sayfanın kendi taşması (ölçüldü:
    // /liquid 20 px tooltip, /solid 9 px katalog tablosu) köşeden bağımsızdır.
    kose_tasma_katkisi: (() => {
      const ile = document.documentElement.scrollWidth;
      const eski = [sekme, panel].map(n => n ? n.style.display : null);
      [sekme, panel].forEach(n => { if (n) n.style.display = 'none'; });
      const siz = document.documentElement.scrollWidth;
      [sekme, panel].forEach((n, i) => { if (n) n.style.display = eski[i]; });
      return ile - siz;
    })(),
  };
}'''

#: Doğrulama paneli kapalıyken 'Göster'in gerekçesi (sözlükteki cümle).
DOGRULAMA_GEREKCESI = {'en': 'Open the Validation panel in the analysis center first.',
                       'tr': 'Önce analiz merkezinde doğrulama panelini açın.'}
#: Köşe başlığı ve .eng gerekçesi (çalışırken dil değişimi bekçisi).
KOSE_BASLIGI = {'en': 'OpenRocket file exchange', 'tr': 'OpenRocket dosya alışverişi'}
ENG_GEREKCESI = {'en': 'Run the motor calculation first.', 'tr': 'Önce motoru hesaplayın.'}
#: Bildirimin örtmemesi gereken köşe öğeleri (denetim Ş2).
ORTULMEYECEKLER = ['orKoseKapat', 'orKoseEngDugme', 'orKoseEngUyari', 'orKoseBaslik']

#: Panel YALNIZ bu yeteneklerin kalemlerini taşır (gerçek + testli küme).
BEKLENEN_KALEMLER = ['orKoseEng', 'orKoseOrk', 'orKoseItki', 'orKoseDogrulama']


def _sayfa_hukumleri(yol, kapali, acik, dil):
    """Bir sayfanın ölçümüne uygulanan hükümler (canlı ya da kayıtlı)."""
    _, _, uc, _ = KOSE_SAYFALARI[yol]
    assert kapali['kuruldu'], yol
    assert kapali['sekme_gorunur'] and not kapali['panel_gorunur'], yol
    assert acik['panel_gorunur'], yol
    assert kapali['disarida_gorunur_or'] == [], (yol, kapali['disarida_gorunur_or'])
    assert kapali['eski_dugme_var'] and kapali['eski_dugme_display'] == 'none', (yol, kapali)
    assert acik['ork_kosede'], yol
    assert acik['eng_uc'] == uc, yol
    assert acik['eng_disabled'] is True, yol
    beklenen = {'en': 'Run the motor calculation first.',
                'tr': 'Önce motoru hesaplayın.'}[dil]
    assert acik['eng_neden'] == beklenen, (yol, acik['eng_neden'])
    assert kapali['kose_tasma_katkisi'] == 0 and acik['kose_tasma_katkisi'] == 0, yol
    # Denetim Ş1 / D10: doğrulama paneli kapalıyken 'Göster' kapalı ve
    # gerekçesi sayfa dilinde (fail-closed yönlendirme).
    assert acik['dog_disabled'] is True, (yol, acik['dog_disabled'])
    assert acik['dog_neden'] == DOGRULAMA_GEREKCESI[dil], (yol, acik['dog_neden'])
    # Denetim Ş1 / D9: sıvıdaki .eng açıklama satırı (li) da gizli; öteki
    # sayfalarda o satır yok.
    if yol == '/liquid':
        assert kapali['eng_li_var'] and kapali['eng_li_display'] == 'none', (yol, kapali)
    else:
        assert not kapali['eng_li_var'], yol


#: Köşe öğelerinin üstünde ne var (denetim Ş2). Her öğe panelin içinde
#: görünüme getirilir; merkezindeki en üst öğe kendisi (ya da çocuğu) olmalı
#: ve sabit konumlu bildirim yığınlarındaki hiçbir bildirim kutusu öğenin
#: dikdörtgeniyle kesişmemeli (#hrma-toast-stack pointer-events:none
#: taşıdığı için elementFromPoint onu görmez; kesişim ayrıca ölçülür).
ORTU_JS = r'''(ids) => {
  const yiginlar = ['toast-stack', 'hrma-toast-stack']
    .map(i => document.getElementById(i)).filter(Boolean);
  const sonuc = {};
  ids.forEach(id => {
    const n = document.getElementById(id);
    if (!n || n.hidden || !n.getClientRects().length) { sonuc[id] = {gorunur: false}; return; }
    n.scrollIntoView({block: 'nearest'});
    const r = n.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    const e = document.elementFromPoint(x, y);
    const kesisen = [];
    yiginlar.forEach(s => Array.from(s.children).forEach(c => {
      const q = c.getBoundingClientRect();
      if (q.width && q.height && q.left < r.right && q.right > r.left
          && q.top < r.bottom && q.bottom > r.top) kesisen.push(s.id);
    }));
    sonuc[id] = {gorunur: true, ustte_kendisi: !!e && (e === n || n.contains(e)),
                 ustteki: e ? String(e.id || e.className || e.tagName).slice(0, 80) : null,
                 kesisen: kesisen};
  });
  sonuc._bildirim = yiginlar.reduce((a, s) => a + s.children.length, 0)
    + document.querySelectorAll('.hrma-notice').length;
  const panel = document.getElementById('orKosePanel');
  sonuc._panel_acik = !panel.hidden;
  sonuc._panel_sol = panel.getBoundingClientRect().left;
  sonuc._panel_itildi = !!panel.style.top;
  const ts = document.getElementById('toast-stack');
  const kutular = ts ? Array.from(ts.children).map(c => c.getBoundingClientRect())
    .filter(q => q.width && q.height) : [];
  sonuc._yigin_sag = kutular.length ? Math.max.apply(null, kutular.map(q => q.right)) : null;
  return sonuc;
}'''

#: Sayfanın KENDİ hata bildirimi (sıvı/katı showError -> showMessage ->
#: #toast-stack; hibrit showError -> showNotice -> #hrmaNotices). Hata
#: bildirimi kalıcıdır ve odağı üstüne alır (sayfa deseni).
BILDIRIM_AC_JS = r'''(metin) => {
  if (typeof window.showError !== 'function') return false;
  window.showError(metin);
  return true;
}'''


#: Ortak bildirim yığını (import_ui.js / project_bar.js toast():
#: #hrma-toast-stack, sağ alt). Bildirimi SAYFANIN kendi işleviyle açar, iki
#: kare bekler (köşenin MutationObserver'ı ve yerleşim) ve yığını ölçer.
#: Denetim-2 Ş1 (3. tur): bu yığın hiçbir adımda açılmıyordu; CSS kaydırması
#: (M3) ve dar ekranda alttaki yığın sınırı (M4) sınanmıyordu.
HRMA_YIGIN_AC_JS = r'''async (metin) => {
  if (!window.HRMAImportUI || typeof window.HRMAImportUI.toast !== 'function')
    return {acildi: false};
  window.HRMAImportUI.toast(metin, 'info');
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const s = document.getElementById('hrma-toast-stack');
  const kutular = s ? Array.from(s.children).map(c => c.getBoundingClientRect())
    .filter(q => q.width && q.height) : [];
  const panel = document.getElementById('orKosePanel');
  const pr = panel.getBoundingClientRect();
  return {
    acildi: true,
    adet: kutular.length,
    yigin_sag: kutular.length ? Math.max.apply(null, kutular.map(q => q.right)) : null,
    yigin_ust: kutular.length ? Math.min.apply(null, kutular.map(q => q.top)) : null,
    panel_acik: !panel.hidden,
    panel_sol: pr.left,
    panel_alt: pr.bottom,
    panel_itildi: !!panel.style.top,
  };
}'''

#: Ölçümden sonra ortak yığını boşaltır (toast()'un kendi 6 s'lik
#: temizliğiyle aynı sonuç: kap boşsa DOM'dan kalkar).
HRMA_YIGIN_TEMIZLE_JS = r'''() => {
  const s = document.getElementById('hrma-toast-stack');
  if (s && s.parentNode) s.parentNode.removeChild(s);
  return 0;
}'''

#: Sunucunun bildirdiği zarf uyarısı kodunu değiştirip köşeyi yeniler.
ZARF_KODU_JS = r'''(kod) => {
  window.currentResults.openrocket.eng_envelope_warning = {error: kod, message: 'x'};
  window.HRMAOpenRocketKose.durumGuncelle();
  return 0;
}'''

#: Köşenin tanımadığı zarf kodu (denetim-2 Ş1): susturulmaz, adıyla söylenir.
BILINMEYEN_ZARF_KODU = 'xyz'
#: Köşenin tanıdığı zarf kodu (ölçümün başlangıç durumu).
BILINEN_ZARF_KODU = 'propellant_outside_envelope'


def _ek_olcum(p):
    """EN sayfada, panel açık ve motor yokken başlar; ölçer ve kaydeder.

    D11: çalışırken dil değişimi (I18N.setLang). D4: zarf uyarısı koddan
    sözlük cümlesine; tanınmayan kod adıyla söylenir (3. tur). Ş2: hata
    bildirimi köşe öğelerini örtmüyor (1440 ve 390 px); bildirimi kapatan
    Esc paneli kapatmıyor. 3. tur: ortak yığın (#hrma-toast-stack) geniş
    ekranda panelin solunda, dar ekranda panelin altında.
    """
    ek = {}
    p.evaluate("() => { I18N.setLang('tr'); return 0; }")
    ek['dil_tr'] = p.evaluate(OLC_JS)
    p.evaluate("() => { I18N.setLang('en'); return 0; }")
    ek['dil_en'] = p.evaluate(OLC_JS)
    p.evaluate("""() => {
        window.currentResults = {motor: {}, openrocket: {
            eng_error: {missing_fields: ['burn_time']},
            eng_envelope_warning: {error: 'propellant_outside_envelope', message: 'x'}}};
        const asil = document.getElementById('downloadEngBtn');
        if (asil) asil.disabled = false;
        window.HRMAOpenRocketKose.durumGuncelle();
    }""")
    ek['zarf'] = p.evaluate(OLC_JS)
    p.evaluate(ZARF_KODU_JS, BILINMEYEN_ZARF_KODU)
    ek['zarf_bilinmeyen'] = p.evaluate(OLC_JS)
    p.evaluate(ZARF_KODU_JS, BILINEN_ZARF_KODU)
    for ad, (gen, yuk) in (('genis', (1440, 900)), ('dar', (390, 844))):
        p.set_viewport_size({'width': gen, 'height': yuk})
        if not p.evaluate("() => !document.getElementById('orKosePanel').hidden"):
            p.click('#orKoseSekme')
        ek[ad + '_bildirim_acildi'] = p.evaluate(BILDIRIM_AC_JS, 'ORKOSE-BILDIRIM-BEKCISI')
        ek[ad] = p.evaluate(ORTU_JS, ORTULMEYECEKLER)
        p.keyboard.press('Escape')
        ek[ad + '_esc_sonrasi'] = p.evaluate(ORTU_JS, [])
        ek[ad + '_hrma_yigin'] = p.evaluate(HRMA_YIGIN_AC_JS, 'ORKOSE-YIGIN-BEKCISI')
        ek[ad + '_hrma_ortu'] = p.evaluate(ORTU_JS, ORTULMEYECEKLER)
        p.evaluate(HRMA_YIGIN_TEMIZLE_JS)
    p.set_viewport_size({'width': 1440, 'height': 900})
    return ek


def _ek_hukumleri(yol, ek, en_sozluk):
    """_ek_olcum kaydına uygulanan hükümler (canlı ya da kayıtlı)."""
    # D11: dil değişimi köşeye işliyor (ve geri dönüyor).
    assert ek['dil_tr']['baslik'] == KOSE_BASLIGI['tr'], (yol, ek['dil_tr']['baslik'])
    assert ek['dil_tr']['eng_neden'] == ENG_GEREKCESI['tr'], (yol, ek['dil_tr']['eng_neden'])
    assert ek['dil_en']['baslik'] == KOSE_BASLIGI['en'], (yol, ek['dil_en']['baslik'])
    assert ek['dil_en']['eng_neden'] == ENG_GEREKCESI['en'], (yol, ek['dil_en']['eng_neden'])
    # D4: zarf uyarısı KODDAN sözlük cümlesine.
    assert ek['zarf']['eng_zarf_kod'] == 'propellant_outside_envelope', (yol, ek['zarf'])
    assert ek['zarf']['eng_zarf'] == en_sozluk['openrocket.kose.warn.envelopeOutside'], yol
    # Denetim-2 Ş1: tanınmayan kod susturulmaz; kod adıyla, sözlük cümlesiyle.
    zb = ek['zarf_bilinmeyen']
    assert zb['eng_zarf_kod'] == BILINMEYEN_ZARF_KODU, (yol, zb)
    assert zb['eng_zarf'] == en_sozluk['openrocket.kose.warn.envelopeUnknown'].replace(
        '{code}', BILINMEYEN_ZARF_KODU), (yol, zb['eng_zarf'])
    # Ş2: bildirim gerçekten açıldı, köşe öğelerini örtmüyor, Esc onu
    # kapatıyor ama paneli kapatmıyor.
    for ad in ('genis', 'dar'):
        assert ek[ad + '_bildirim_acildi'] is True, (yol, ad)
        o = ek[ad]
        assert o['_bildirim'] >= 1 and o['_panel_acik'], (yol, ad, o)
        for oge in ORTULMEYECEKLER:
            assert o[oge]['gorunur'], (yol, ad, oge, o[oge])
            assert o[oge]['ustte_kendisi'], (yol, ad, oge, o[oge])
            assert o[oge]['kesisen'] == [], (yol, ad, oge, o[oge])
        if ad == 'genis' and o['_yigin_sag'] is not None:
            # Geniş ekranda yığın panelin SOLUNA kayar; panel yerinde kalır.
            assert o['_yigin_sag'] <= o['_panel_sol'], (yol, o['_yigin_sag'], o['_panel_sol'])
            assert not o['_panel_itildi'], yol
        sonra = ek[ad + '_esc_sonrasi']
        assert sonra['_panel_acik'], (yol, ad, 'bildirimi kapatan Esc paneli kapattı')
        assert sonra['_bildirim'] == o['_bildirim'] - 1, (yol, ad, o['_bildirim'], sonra['_bildirim'])
        # Denetim-2 Ş1: ortak yığın (#hrma-toast-stack). Geniş ekranda yığın
        # panelin SOLUNDA, panel yerinde; dar ekranda panel yığının ÜSTÜNDE
        # biter. Köşe öğelerinin hiçbiri yığındaki bildirimle kesişmez.
        y = ek[ad + '_hrma_yigin']
        assert y['acildi'] is True and y['adet'] >= 1 and y['panel_acik'], (yol, ad, y)
        if ad == 'genis':
            assert y['yigin_sag'] <= y['panel_sol'], (yol, ad, y['yigin_sag'], y['panel_sol'])
            assert not y['panel_itildi'], (yol, ad, y)
        else:
            assert y['panel_alt'] <= y['yigin_ust'], (yol, ad, y['panel_alt'], y['yigin_ust'])
        oy = ek[ad + '_hrma_ortu']
        assert oy['_bildirim'] >= 1 and oy['_panel_acik'], (yol, ad, oy)
        for oge in ORTULMEYECEKLER:
            assert oy[oge]['gorunur'], (yol, ad, oge, oy[oge])
            assert oy[oge]['ustte_kendisi'], (yol, ad, oge, oy[oge])
            assert oy[oge]['kesisen'] == [], (yol, ad, oge, oy[oge])


def _tarayici_ac(pw):
    from tools.browser_harness import tur
    tarayici, _, _ = tur._tarayici_ac(pw, 'auto', False)
    return tarayici


def _canli_tarayici_mumkun():
    if importlib.util.find_spec('playwright') is None:
        return False, 'playwright paketi yok'
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            _tarayici_ac(pw).close()
        return True, ''
    except Exception as hata:  # tarayıcı ikilisi yok
        return False, str(hata)[:200]


class TestTarayici:
    def test_uc_sayfada_sekme_panel_gizleme_ve_kapi(self):
        mumkun, neden = _canli_tarayici_mumkun()
        if not mumkun and os.environ.get('HRMA_ORKOSE_CANLI_ZORUNLU'):
            # Ters mutasyon koşusu canlı yolu ister: kayıtlı ölçüme düşmek
            # mutasyonu göremez (sahte yeşil).
            pytest.fail('canlı tarayıcı zorunlu ama açılamadı: %s' % neden)
        if not mumkun:
            # Kayıtlı ölçüm (kesif betiğinin çıktısı) aynı hükümlerden geçer.
            kayit = json.loads(_oku(kanit_gerekli(TARAYICI_KANIT)))
            for yol in KOSE_SAYFALARI:
                for dil in ('en', 'tr'):
                    r = kayit['%s_%s' % (yol.strip('/'), dil)]
                    _sayfa_hukumleri(yol, r['kapali'], r['acik'], dil)
                    if dil == 'en':
                        _ek_hukumleri(yol, r['ek'], dict(_sozluk_bloklari()[0]))
            return

        from playwright.sync_api import sync_playwright
        from tools.browser_harness.sunucu import UygulamaSunucusu
        with UygulamaSunucusu() as s, sync_playwright() as pw:
            tarayici = _tarayici_ac(pw)
            try:
                for yol, (_, secici, _, islev) in KOSE_SAYFALARI.items():
                    for dil in ('en', 'tr'):
                        b = tarayici.new_context(viewport={'width': 1440, 'height': 900})
                        b.add_init_script("try{localStorage.setItem('hrma_lang','%s')}catch(e){}" % dil)
                        p = b.new_page()
                        hatalar = []
                        p.on('pageerror', lambda e: hatalar.append(str(e)))
                        p.goto(s.temel_url + yol, wait_until='load', timeout=120000)
                        p.wait_for_function('() => window.HRMAOpenRocketKose'
                                            ' && window.HRMAOpenRocketKose.kuruldu()', timeout=30000)
                        kapali = p.evaluate(OLC_JS)
                        p.click('#orKoseSekme')
                        acik = p.evaluate(OLC_JS)
                        _sayfa_hukumleri(yol, kapali, acik, dil)
                        assert not [h for h in hatalar if 'openrocket_kose' in h], hatalar

                        kalemler = p.evaluate("() => Array.from(document.querySelectorAll("
                                              "'#orKosePanel .or-kose-kalem')).map(n => n.id)")
                        assert kalemler == BEKLENEN_KALEMLER, kalemler

                        # Eski düğme DOM'da, kimliği/onclick'i yerinde, yalnız gizli.
                        assert p.evaluate("(s) => { const n = document.querySelector(s);"
                                          " return !!n && n.getClientRects().length === 0; }",
                                          secici)

                        if dil == 'en':
                            _ek_hukumleri(yol, _ek_olcum(p), dict(_sozluk_bloklari()[0]))
                            # Fail-closed kapı açılır + vekâlet sayfanın KENDİ işlevini çağırır.
                            p.evaluate("""(islev) => {
                                window.__orSayac = 0;
                                window[islev] = function () { window.__orSayac += 1; };
                                window.currentResults = {motor: {}, openrocket: {eng_error:
                                    {missing_fields: ['burn_time']}}};
                                const asil = document.getElementById('downloadEngBtn');
                                if (asil) asil.disabled = false;
                                window.HRMAOpenRocketKose.durumGuncelle();
                            }""", islev)
                            d = p.evaluate(OLC_JS)
                            assert d['eng_disabled'] is False and d['eng_neden'] is None, d
                            assert d['eng_uyari'] and 'burn_time' in d['eng_uyari'], d
                            p.click('#orKoseEngDugme')
                            assert p.evaluate('() => window.__orSayac') == 1

                            # Esc paneli kapatır.
                            p.keyboard.press('Escape')
                            assert p.evaluate(OLC_JS)['panel_gorunur'] is False
                        b.close()
            finally:
                tarayici.close()


# ---------------------------------------------------------------------------
# 4. Uyumluluk: kurulu OpenRocket ile ölçüm
# ---------------------------------------------------------------------------

JAVA_DENETCI = r'''
import info.openrocket.core.file.motor.RASPMotorLoader;
import info.openrocket.core.motor.ThrustCurveMotor;
import java.io.FileInputStream;
import java.io.InputStream;
import java.util.List;

public class OrMotorOku {
    public static void main(String[] args) throws Exception {
        int hata = 0;
        for (String yol : args) {
            try (InputStream in = new FileInputStream(yol)) {
                List<ThrustCurveMotor.Builder> b = new RASPMotorLoader().load(in, yol);
                if (b.isEmpty()) { System.out.println("BOS " + yol); hata++; continue; }
                for (ThrustCurveMotor.Builder x : b) {
                    ThrustCurveMotor m = x.build();
                    System.out.println("OK " + yol + " " + m.getDesignation() + " "
                        + m.getTotalImpulseEstimate() + " " + m.getTimePoints().length + " "
                        + m.getAverageThrustEstimate() + " " + m.getBurnTimeEstimate());
                }
            } catch (Exception e) {
                hata++;
                System.out.println("HATA " + yol + " " + e);
            }
        }
        System.exit(hata == 0 ? 0 : 2);
    }
}
'''


def _or_jar():
    if not OR_JAR_DIZINI.is_dir():
        return None
    jarlar = sorted(OR_JAR_DIZINI.glob('OpenRocket-*.jar'))
    return jarlar[0] if jarlar else None


def _or_surum():
    with open(OR_APP / 'Contents' / 'Info.plist', 'rb') as f:
        return plistlib.load(f).get('CFBundleShortVersionString')


def _javac():
    yol = shutil.which('javac')
    if not yol:
        return None
    try:
        subprocess.run([yol, '-version'], capture_output=True, timeout=30, check=True)
    except Exception:
        return None
    return yol


def _fikstur_yukleri():
    yukler = json.loads(_oku(KOK / 'tests' / 'support' / 'uc_yukleri.json'))
    eng = json.loads(json.dumps(yukler['/api/export-eng']))
    eng['motor_data']['motor_name'] = 'ORKOSE-ENG'
    orx = json.loads(json.dumps(yukler['/api/export-openrocket']))
    orx['motor_data']['motor_name'] = 'ORKOSE-HIB'
    return eng, orx


# ---------------------------------------------------------------------------
# 5. RASP künyesi (UI openrocket-kose 2. tur, devir D1 ve D2)
# ---------------------------------------------------------------------------

#: OpenRocket 24.12 AbstractMotorLoader.removeDelay (jar'dan javap ile okundu):
#: künye bu ifadeye UYARSA son '-' parçası gecikme sayılıp kesilir.
OR_GECIKME_KALIBI = re.compile(r'.*-([0-9]+|[pP])')


def _motor_satiri(eng):
    for satir in eng.splitlines():
        if satir.strip() and not satir.startswith(';'):
            return satir.split()
    raise AssertionError('RASP motor satırı yok')


def _egri_ortalama_itki(t, f):
    """Kâhin: eğrinin trapez integrali / süresi (ürün kodundan bağımsız)."""
    t = [float(x) for x in t]
    f = [float(x) for x in f]
    integral = sum((t[i + 1] - t[i]) * (f[i] + f[i + 1]) / 2.0 for i in range(len(t) - 1))
    return integral / (t[-1] - t[0])


class TestRaspAdi:
    """Künye ``<sınıf><ortalama itki N>-<ad>``; OpenRocket adı kesmez."""

    def _ihracatci(self):
        from hrma.export.openrocket_integration import OpenRocketExporter
        return OpenRocketExporter()

    def test_kunye_sayisi_egriden_ortalama_itki(self):
        # Toplam impuls ve süre alanı YOK: ikisi de yazılan eğriden gelir.
        t = [0.0, 0.1, 0.5, 1.0, 1.8, 2.2]
        f = [0.0, 1500.0, 1400.0, 1300.0, 1100.0, 0.0]
        md = {'motor_name': 'ORKOSE-EGRI', 'thrust_curve': {'time': t, 'thrust': f}}
        beklenen = int(_egri_ortalama_itki(t, f) + 0.5)
        kunye = self._ihracatci()._designation(md)
        assert re.fullmatch(r'[A-O]%d-ORKOSE-EGRI' % beklenen, kunye), (kunye, beklenen)

    def test_kunye_sayisi_impuls_bolu_yanma_suresi(self):
        md = {'motor_name': 'ORKOSE-ALAN', 'total_impulse': 2959.642271652302,
              'burn_time': 2.2771563941946757}
        beklenen = int(2959.642271652302 / 2.2771563941946757 + 0.5)
        assert self._ihracatci()._designation(md) == 'L%d-ORKOSE-ALAN' % beklenen

    def test_kunye_sayisi_yarim_yukari_yuvarlanir(self):
        # Denetim-2 Ş2 (a): I / t tam ,5'e düşer: 5,0 / 2,0 = 2,5 -> 3.
        # Python round() yarımı çifte yuvarlar (2,5 -> 2); kural yarım yukarı.
        md = {'motor_name': 'ORKOSE-YARIM', 'total_impulse': 5.0, 'burn_time': 2.0}
        kunye = self._ihracatci()._designation(md)
        assert re.fullmatch(r'[A-O]3-ORKOSE-YARIM', kunye), kunye

    def test_kunye_suresi_egrinin_ilk_aninden(self):
        # Denetim-2 Ş2 (b): eğri t0 != 0'dan başlar. Süre t[-1] - t[0]; t[-1]
        # tek başına süreyi uzatır ve sayıyı küçültür.
        t = [0.5, 0.6, 1.0, 1.5, 2.3, 2.7]
        f = [0.0, 1500.0, 1400.0, 1300.0, 1100.0, 0.0]
        md = {'motor_name': 'ORKOSE-T0', 'thrust_curve': {'time': t, 'thrust': f}}
        beklenen = int(_egri_ortalama_itki(t, f) + 0.5)
        kunye = self._ihracatci()._designation(md)
        assert re.fullmatch(r'[A-O]%d-ORKOSE-T0' % beklenen, kunye), (kunye, beklenen)

    @pytest.mark.parametrize('md', [
        {},
        {'total_impulse': 5000.0},                       # süre yok, eğri yok
        {'burn_time': 3.0},                              # impuls yok
        {'total_impulse': 2.0, 'burn_time': 5.0},        # 0,4 N -> 1 N'un altı
    ])
    def test_kunye_eksik_veride_uydurmaz(self, md):
        assert self._ihracatci()._designation(md).startswith('UNKNOWN-')

    @pytest.mark.parametrize('ad, beklenen', [
        ('HRMA-001', 'HRMA_001'),
        ('ORKOSE-12', 'ORKOSE_12'),
        ('KISA-P', 'KISA_P'),
        ('kisa-p', 'kisa_p'),
        ('001', '_001'),
        ('P', '_P'),
        ('X-1-2', 'X-1_2'),
        ('HRMA-SOLID', 'HRMA-SOLID'),
        ('D17-P5B209', 'D17-P5B209'),
        ('HRMA_001', 'HRMA_001'),
    ])
    def test_ad_openrocket_gecikmesi_sanilmaz(self, ad, beklenen):
        from hrma.export.openrocket_integration import _sanitize_motor_name
        temiz, beyan = _sanitize_motor_name(ad)
        assert temiz == beklenen
        assert not OR_GECIKME_KALIBI.fullmatch('L1000-' + temiz), temiz
        if temiz == ad:
            assert beyan is None
        else:
            assert beyan and 'removeDelay' in beyan and repr(temiz) in beyan, beyan

    def test_varsayilan_ad_kesilmez(self):
        from hrma.export.openrocket_integration import DEFAULT_MOTOR_NAME
        assert not OR_GECIKME_KALIBI.fullmatch('L1000-' + DEFAULT_MOTOR_NAME)
        assert self._ihracatci()._designation({}) == 'UNKNOWN-' + DEFAULT_MOTOR_NAME

    def test_uc_adi_degistirince_eng_yorumunda_beyan_eder(self, istemci):
        eng_yuk, _ = _fikstur_yukleri()
        eng_yuk['motor_data']['motor_name'] = 'ORKOSE-001'
        r = istemci.post('/api/export-eng', json=eng_yuk).get_json()
        assert r['status'] == 'success', r
        alanlar = _motor_satiri(r['content'])
        md = eng_yuk['motor_data']
        beklenen = int(md['total_impulse'] / md['burn_time'] + 0.5)
        assert alanlar[0] == 'L%d-ORKOSE_001' % beklenen, alanlar
        beyanlar = [x for x in r['content'].splitlines()
                    if x.startswith('; motor name written as')]
        assert len(beyanlar) == 1 and 'removeDelay' in beyanlar[0], beyanlar


class TestUyumluluk:
    def test_disa_aktarilan_eng_kurulu_openrocket_ile_okunur(self, istemci, tmp_path):
        olcum = _js_nesnesi('OLCUM')
        jar = _or_jar()
        javac = _javac()
        if not (jar and OR_JRE.exists() and javac):
            kayit = json.loads(_oku(kanit_gerekli(UYUMLULUK_KANIT)))
            assert kayit['openrocket_surum'] == olcum['openrocket_surum']
            assert olcum['eng_okundu'] is True
            assert kayit['eng'] and all(r['durum'] == 'OK' for r in kayit['eng'])
            assert {r['uc'] for r in kayit['eng']} >= {'/api/export-eng', '/api/export-openrocket'}
            return

        assert _or_surum() == olcum['openrocket_surum'], (
            'kurulu OpenRocket sürümü köşedeki ölçüm sabitinden farklı: yeniden ölç')
        eng_yuk, orx_yuk = _fikstur_yukleri()
        r1 = istemci.post('/api/export-eng', json=eng_yuk).get_json()
        r2 = istemci.post('/api/export-openrocket', json=orx_yuk).get_json()
        assert r1['status'] == 'success' and r2['status'] == 'success'
        a = tmp_path / 'export_eng.eng'
        b = tmp_path / 'export_openrocket.eng'
        a.write_text(r1['content'], encoding='utf-8')
        b.write_text(r2['eng_file_content'], encoding='utf-8')

        (tmp_path / 'OrMotorOku.java').write_text(JAVA_DENETCI, encoding='utf-8')
        derle = subprocess.run([javac, '--release', '17', '-cp', str(jar), '-d', str(tmp_path),
                                str(tmp_path / 'OrMotorOku.java')],
                               capture_output=True, text=True, timeout=180)
        assert derle.returncode == 0, derle.stderr
        kos = subprocess.run([str(OR_JRE), '-Djava.awt.headless=true', '-cp',
                              '%s%s%s' % (jar, os.pathsep, tmp_path), 'OrMotorOku', str(a), str(b)],
                             capture_output=True, text=True, timeout=180)
        assert kos.returncode == 0, kos.stdout + kos.stderr
        satirlar = [s for s in kos.stdout.splitlines() if s.strip()]
        assert len(satirlar) == 2 and all(s.startswith('OK ') for s in satirlar), satirlar
        assert 'ORKOSE-ENG' in satirlar[0] and 'ORKOSE-HIB' in satirlar[1]
        assert olcum['eng_okundu'] is True

    def test_openrocket_kunyeyi_kesmeden_ortalama_itkiyle_okur(self, istemci, tmp_path):
        """Devir D1 + D2: üç motor tipinde OpenRocket'in KENDİ yükleyicisi
        künyeyi HRMA'nın yazdığı gibi okur (gecikme kesilmez) ve künyedeki
        sayı yükün impuls / süresidir."""
        jar = _or_jar()
        javac = _javac()
        if not (jar and OR_JRE.exists() and javac):
            kayit = json.loads(_oku(kanit_gerekli(UYUMLULUK_KANIT)))
            satirlar = kayit['kunye']['satirlar']
            assert len(satirlar) == 4
            for r in satirlar:
                assert r['openrocket_kunye'] == r['hrma_kunye'], r
            return
        eng_yuk, orx_yuk = _fikstur_yukleri()
        sivi_yuk = json.loads(json.dumps(eng_yuk))
        sivi_yuk['motor_data']['motor_type'] = 'liquid'
        sivi_yuk['motor_data']['motor_name'] = 'ORKOSE-SIVI'
        varsayilan = json.loads(json.dumps(eng_yuk))
        del varsayilan['motor_data']['motor_name']
        # Uçlar LİTERAL yazılır (test_d24 rota çözücüsü değişkenli çağrıyı
        # çözemez; kör nokta büyümesin).
        yanitlar = [
            ('content', eng_yuk, istemci.post('/api/export-eng', json=eng_yuk).get_json()),
            ('content', sivi_yuk, istemci.post('/api/export-eng', json=sivi_yuk).get_json()),
            ('eng_file_content', orx_yuk,
             istemci.post('/api/export-openrocket', json=orx_yuk).get_json()),
            ('content', varsayilan, istemci.post('/api/export-eng', json=varsayilan).get_json()),
        ]
        dosyalar, beklenen = [], []
        for i, (alan, yuk, r) in enumerate(yanitlar):
            assert r['status'] == 'success', (alan, r)
            yol = tmp_path / ('kunye_%d.eng' % i)
            yol.write_text(r[alan], encoding='utf-8')
            dosyalar.append(str(yol))
            md = yuk['motor_data']
            sayi = int(md['total_impulse'] / md['burn_time'] + 0.5)
            kunye = _motor_satiri(r[alan])[0]
            assert re.fullmatch(r'[A-O]%d-.+' % sayi, kunye), (kunye, sayi)
            beklenen.append(kunye)
        assert beklenen[3].endswith('-HRMA_001'), beklenen[3]
        (tmp_path / 'OrMotorOku.java').write_text(JAVA_DENETCI, encoding='utf-8')
        derle = subprocess.run([javac, '--release', '17', '-cp', str(jar), '-d', str(tmp_path),
                                str(tmp_path / 'OrMotorOku.java')],
                               capture_output=True, text=True, timeout=180)
        assert derle.returncode == 0, derle.stderr
        kos = subprocess.run([str(OR_JRE), '-Djava.awt.headless=true', '-cp',
                              '%s%s%s' % (jar, os.pathsep, tmp_path), 'OrMotorOku'] + dosyalar,
                             capture_output=True, text=True, timeout=180)
        assert kos.returncode == 0, kos.stdout + kos.stderr
        satirlar = [x.split() for x in kos.stdout.splitlines() if x.strip()]
        assert [x[2] for x in satirlar] == beklenen, (satirlar, beklenen)

    def test_openrocket_ornek_ork_sayisi_kose_sabitiyle_ayni(self, istemci):
        olcum = _js_nesnesi('OLCUM')
        jar = _or_jar()
        if not jar:
            kayit = json.loads(_oku(kanit_gerekli(UYUMLULUK_KANIT)))
            ork = kayit['ork_ornekleri']
            assert sum(1 for r in ork if r['status'] == 'success') == olcum['ork_ornek_okunan']
            assert len(ork) == olcum['ork_ornek_toplam']
            return

        okunan = 0
        toplam = 0
        with zipfile.ZipFile(jar) as z:
            for ad in sorted(z.namelist()):
                if not (ad.startswith('datafiles/examples/') and ad.endswith('.ork')):
                    continue
                toplam += 1
                r = istemci.post('/api/import/ork',
                                 data={'file': (io.BytesIO(z.read(ad)), os.path.basename(ad))},
                                 content_type='multipart/form-data')
                j = r.get_json() or {}
                if r.status_code == 200 and j.get('status') == 'success':
                    okunan += 1
        assert toplam == olcum['ork_ornek_toplam'], (toplam, olcum)
        assert okunan == olcum['ork_ornek_okunan'], (okunan, olcum)
