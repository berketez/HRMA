"""V301/DİL-2 — yayın kapısı 7: dil bekçisi ANAHTARI değil EKRANI ölçer.

Kök 7 (``feedback-yayin-kapilari-v301``): 3.0.0'ın dil bekçisi sözlük
anahtarlarını sayıyordu; TR ekranda kalan İngilizce cümleyi, ham makine
anahtarını ve kaynak yolunu görmüyordu (26 Eki son kullanıcı turu: NK-7,
NK-11, NK-16, NK-35/36, NK-67 …). Bu bekçi ekranın kendisine bakar:

* Üç motor sayfası (hibrit / katı / sıvı) TR arayüzde, 1280 px.
* Paketteki örnek proje açılır (``?project=``), Hesapla'ya basılır, grafik
  sayısı durulana kadar beklenir; analiz güvertesi ızgara kipine alınır ve
  görünür bütün sekme düğmeleri sırayla tıklanır. Her durumda GÖRÜNEN metin
  düğümleri toplanır (kapalı ``<details>`` içeriği, gizli/opaklığı 0 öğe,
  sıfır boyutlu kutu sayılmaz).
* Sınıflar (ölçüm düzeneği ``docs/scofield/raw/OH/V301/dil-2/olcum.py`` ile
  AYNI kurallar; bekçi docs'a bağlı değildir, kurallar burada yazılı):
    a) ham anahtar — snake_case sözcük, noktalı anahtar (a.b.c), ``/api/…``
    b) İngilizce cümle — >= 4 ardışık yaygın İngilizce sözcük
    c) kaynak/iç kod — ``hrma/…``, ``tests/…``, ``….py``, ``hrma.x.y``,
       ``OH-…``, ``P6B1-07`` biçimli defter kodu

Muafiyetler parça (token) düzeyindedir ve her biri GEREKÇELİDİR (formül
simgesi, sürüm etiketi, tarayıcının kendi metni, denetçi kararıyla makine
kimliği). Bir metin düğümü muaf olmayan tek bir parça taşıyorsa bulgudur.
Muafiyet listesine ekleme, bulguyu susturmanın yolu DEĞİLDİR: yeni bir
parça ekranda göründüğünde önce düzeltilir; muafiyet ancak parça gerçekten
formül/özel ad/birim ise, gerekçesiyle eklenir.

Eşik: sayfa başına muaf olmayan bulgu 0 (V301/DİL-2 sonu ölçüm, 27 Eki;
önce 82 ham anahtar, 14 İngilizce cümle, 4 kaynak yolu — dil-2/once.json).
"""
import json
import os
import re
import shutil
from pathlib import Path

import pytest

from tests.test_v301_kati_yakit_kimligi import CHROME  # tek tanım orada

KOK = Path(__file__).resolve().parents[1]
ORNEKLER = KOK / 'examples'

#: sayfa → (örnek proje dosyası, Hesapla düğmesinin onclick'i)
DIL_EKRAN_SAYFALARI = {
    'hybrid': ('Example Hybrid N2O-HTPB 3kN.hrma', 'calculate()'),
    'solid': ('Example Solid KNDX BATES 75mm.hrma', 'calculateSolid()'),
    'liquid': ('Example Liquid LOX-RP1 25kN.hrma', 'calculateLiquid()'),
}


def _tarayici_var():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return os.path.exists(CHROME)


# ---------------------------------------------------------------------------
# Sınıflandırma kuralları (olcum.py ile aynı)
# ---------------------------------------------------------------------------
EN = set("""the a an of to in on for with and or is are was were be been not no this that these those it its
by from as at if then than when while which who what where how all any each other some such only also more most
less very can cannot will would should must may might do does did done has have had use used using uses set run
runs result results value values input inputs output outputs supplied given computed estimated based per into
over under above below between before after because so but there their they we you your our one two zero
default defaults missing invalid error warning note see check please must requires required required. available
not calculated calculation calculate total mass pressure temperature chamber nozzle exit flow rate thrust design
model models modelled modeled only applied apply source data table method mode case cases out up down same
here now just like below above full first last new old off true false none null yet still own both either
through without within about against along across during per being make makes made get gets got show shows
shown solver solve solved budget iteration iterations outlet inlet wall grid order""".split())
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
RX_ANAHTAR = [re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b"),
              re.compile(r"\b[a-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+){2,}\b"),
              re.compile(r"/api/[\w\-/]+")]
RX_KOD = [re.compile(r"\bhrma/[\w/.\-]+"), re.compile(r"\btests/[\w/.\-]+"),
          re.compile(r"\b[\w\-]+\.py\b"),
          re.compile(r"\bhrma\.[a-z_]+(?:\.[a-z_]+)*\b"),
          re.compile(r"\bOH-[A-Z0-9][A-Z0-9\-]*\b"), re.compile(r"\bP\d+B\d+-\d+\b")]

#: Parça muafiyetleri — (parça, gerekçe). Parça TAM eşleşir.
MUAF_PARCALAR = {
    # Formül simgeleri (alt çizgi alt indistir; çevrilecek bir ad değil)
    'p_e': 'formül simgesi: çıkış basıncı',
    'p_a': 'formül simgesi: ortam basıncı',
    'p_c': 'formül simgesi: oda basıncı',
    'p_w': 'formül simgesi: cidar basıncı (ayrılma hükmü)',
    'p_v': 'formül simgesi: buhar basıncı (IEC 60534 bağıntısı)',
    'h_gaz': 'formül simgesi: gaz tarafı ısı taşınım katsayısı (Bartz)',
    'eta_c': 'formül simgesi: c* verimi (η_c*)',
    'eta_kin': 'formül simgesi: kinetik verim',
    't_b': 'formül simgesi: yanma süresi',
    'd_j': 'formül simgesi: jet çapı (serbest jet boyu 6·d_j)',
    'mu_b': 'formül simgesi: yığın viskozitesi (Sieder-Tate)',
    'mu_w': 'formül simgesi: cidar viskozitesi (Sieder-Tate)',
    'mdot_ox': 'formül simgesi: oksitleyici debisi (F/ṁ_ox)',
    'mdot_total': 'formül simgesi: toplam debi (itki eğrisi bağıntısı)',
    'c_star': 'formül simgesi: karakteristik hız (itki eğrisi bağıntısı)',
    't_residual': 'formül simgesi: artık et kalınlığı (zarf bağıntısı)',
    'h_ig': 'formül simgesi: ideal gaz entalpisi (kaynak künyesi)',
    'h_sat_liquid': 'formül simgesi: doymuş sıvı entalpisi (kaynak künyesi)',
    # Tarayıcının kendi metni (başsız Chromium'da WebGL yok; 3B kitaplığın
    # yedek iletisi — gerçek kullanıcı tarayıcısında çıkmaz)
    'get.webgl.org': 'başsız tarayıcının WebGL yok iletisi (kitaplık metni)',
}
#: Kalıp muafiyetleri — (parça regex'i, metin bağlamı regex'i ya da None,
#: gerekçe). Bağlam verilmişse muafiyet YALNIZ o bağlamı taşıyan metinde
#: geçerlidir (aynı ad başka cümlede alan adı olarak çıkarsa bulgudur).
MUAF_KALIPLAR = [
    (re.compile(r'^v\d+\.\d+\.\d+$'), None,
     'sürüm etiketi (noktalı sürüm anahtar değil)'),
    # D37 · A1c denetçi Ş1 (D10) kararı: yanma panosu koşu noktası notunda
    # çıkış künyesi kodu MAKİNE kimliği olarak AYNEN; kilit:
    # tests/test_d37_panel_dil_a1.py (G2). Kök 7 ile çelişkisi ana modele
    # DEVİR (V301/DİL-2 RAPOR §DEVİR).
    (re.compile(r'^(?:sea_level_default(?:_equilibrium)?|'
                r'(?:supplied_)?expansion_ratio(?:_equilibrium)?)$'),
     re.compile(r'çıkış künyesi|tarama eğrisiyle aynı çıkış çapası'),
     'çıkış künyesi kodu (D10 denetçi kararı, test_d37_panel_dil_a1 kilidi)'),
]


def _muaf(parca, metin=''):
    if parca in MUAF_PARCALAR:
        return True
    for rx, baglam, _ in MUAF_KALIPLAR:
        if rx.match(parca) and (baglam is None or baglam.search(metin)):
            return True
    return False


def ingilizce(s):
    run = best = 0
    for t in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü'\-]+", s):
        if t.lower() in EN and WORD.fullmatch(t):
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best >= 4


def anahtarlar(s):
    out = []
    for rx in RX_ANAHTAR:
        out += rx.findall(s)
    return [x for x in out if not re.fullmatch(r"[\d._]+", x) and '@' not in x]


def kodlar(s):
    out = []
    for rx in RX_KOD:
        out += rx.findall(s)
    return out


def siniflandir(havuz):
    """havuz: {metin: kapsayıcı kimlik} → muaf olmayan bulgular."""
    bulgu = {'ham_anahtar': {}, 'ingilizce': {}, 'kod': {}}
    for t, kid in havuz.items():
        k = [x for x in anahtarlar(t) if not _muaf(x, t)]
        if k:
            bulgu['ham_anahtar'][t] = {'kap': kid, 'parca': k[:4]}
        if ingilizce(t):
            bulgu['ingilizce'][t] = {'kap': kid}
        kk = [x for x in kodlar(t) if not _muaf(x, t)]
        if kk:
            bulgu['kod'][t] = {'kap': kid, 'parca': kk[:4]}
    return bulgu


JS_METIN = r"""() => {
  const out = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const t = n.textContent.replace(/\s+/g, ' ').trim();
    if (t.length < 2) continue;
    const p = n.parentElement; if (!p) continue;
    if (['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','OPTION'].includes(p.tagName)) continue;
    const st = getComputedStyle(p);
    if (st.visibility === 'hidden' || st.display === 'none' || parseFloat(st.opacity) === 0) continue;
    const r = document.createRange(); r.selectNodeContents(n);
    const rc = r.getBoundingClientRect();
    if (rc.width < 1 || rc.height < 1) continue;
    let gizli = false;
    for (let e = p; e && e !== document.body; e = e.parentElement) {
      if (e.tagName === 'DETAILS' && !e.open) {
        const ozet = e.querySelector(':scope > summary');
        if (!(ozet && ozet.contains(p))) { gizli = true; break; }
      }
    }
    if (gizli) continue;
    const kap = p.closest('[id]');
    out.push([t.slice(0, 400), kap ? kap.id : '']);
  }
  for (const s of document.querySelectorAll('select')) {
    if (!s.offsetParent) continue;
    const o = s.options[s.selectedIndex]; if (o) out.push([o.textContent.trim(), s.id || '']);
  }
  return out;
}"""


def _topla(pg, havuz):
    for t, kid in pg.evaluate(JS_METIN):
        havuz.setdefault(t, kid)


def _sekmeleri_gez(pg, havuz):
    try:
        pg.evaluate("""() => { const b = document.querySelector('.ad-layout-btn[data-layout="grid"]');
            if (b) b.click(); }""")
        pg.wait_for_timeout(800)
        _topla(pg, havuz)
    except Exception:
        pass
    n = pg.evaluate("() => document.querySelectorAll('.tab-button, .subtab-button, [role=tab]').length")
    for i in range(n):
        ok = pg.evaluate("""(i) => { const b = document.querySelectorAll('.tab-button, .subtab-button, [role=tab]')[i];
            if (!b || !b.offsetParent) return false; b.click(); return true; }""", i)
        if ok:
            pg.wait_for_timeout(350)
            _topla(pg, havuz)


@pytest.fixture(scope='module')
def ekran(tmp_path_factory):
    """Üç sayfanın TR ekran metni (örnek yüklü + hesaplanmış)."""
    if not _tarayici_var():
        pytest.skip('playwright/chromium yok')
    from playwright.sync_api import sync_playwright
    from tools.browser_harness.sunucu import UygulamaSunucusu
    dizin = tmp_path_factory.mktemp('dil_ekran_projeler')
    for dosya, _ in DIL_EKRAN_SAYFALARI.values():
        shutil.copy(ORNEKLER / dosya, dizin / dosya)
    eski = os.environ.get('HRMA_PROJECTS_DIR')
    os.environ['HRMA_PROJECTS_DIR'] = str(dizin)
    sonuc = {}
    try:
        with UygulamaSunucusu() as s, sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME, headless=True,
                                    args=['--disable-3d-apis', '--disable-gpu',
                                          '--use-gl=disabled'])
            try:
                for ad, (dosya, hesap) in DIL_EKRAN_SAYFALARI.items():
                    ctx = br.new_context(viewport={'width': 1280, 'height': 900},
                                         locale='tr-TR')
                    ctx.add_init_script("try{localStorage.setItem('hrma_lang','tr')}catch(e){}")
                    pg = ctx.new_page()
                    pg.set_default_timeout(30000)
                    proje = json.loads((dizin / dosya).read_text(encoding='utf-8'))['name']
                    pg.goto(s.temel_url + '/' + ad + '?project='
                            + __import__('urllib.parse').parse.quote(proje))
                    pg.wait_for_timeout(2500)
                    pg.locator('button[onclick="%s"]' % hesap).first.click()
                    onceki, sabit = -1, 0
                    for _ in range(90):
                        pg.wait_for_timeout(1000)
                        nn = pg.evaluate("() => Array.from(document.querySelectorAll('.js-plotly-plot'))"
                                         ".filter(g => g.offsetParent).length")
                        sabit = sabit + 1 if (nn == onceki and nn > 0) else 0
                        onceki = nn
                        if sabit >= 3:
                            break
                    havuz = {}
                    _topla(pg, havuz)
                    _sekmeleri_gez(pg, havuz)
                    sonuc[ad] = {'havuz': havuz, 'grafik': onceki}
                    ctx.close()
            finally:
                br.close()
    finally:
        if eski is None:
            os.environ.pop('HRMA_PROJECTS_DIR', None)
        else:
            os.environ['HRMA_PROJECTS_DIR'] = eski
    return sonuc


@pytest.mark.parametrize('sayfa', sorted(DIL_EKRAN_SAYFALARI))
def test_ornek_hesaplandi_ve_ekran_olculdu(ekran, sayfa):
    """Ön koşul: ölçüm boş ekranda yapılmadı (hesap koştu, grafik çizildi)."""
    d = ekran[sayfa]
    assert d['grafik'] > 0, '%s: hesaptan sonra görünür grafik yok' % sayfa
    assert len(d['havuz']) > 500, (
        '%s: yalnız %d görünür metin düğümü — sayfa yüklenmemiş ya da hesap '
        'koşmamış' % (sayfa, len(d['havuz'])))


@pytest.mark.parametrize('sayfa', sorted(DIL_EKRAN_SAYFALARI))
@pytest.mark.parametrize('sinif', ['ham_anahtar', 'ingilizce', 'kod'])
def test_tr_ekranda_sizinti_yok(ekran, sayfa, sinif):
    """TR ekranda muaf olmayan ham anahtar / İngilizce cümle / kaynak yolu 0."""
    bulgu = siniflandir(ekran[sayfa]['havuz'])[sinif]
    ozet = ['%s#%s: %s %s' % (sayfa, v['kap'] or '(kimliksiz)', t[:160],
                               v.get('parca', '')) for t, v in bulgu.items()]
    assert not bulgu, ('%s TR ekranında %d %s bulgusu:\n  %s'
                       % (sayfa, len(bulgu), sinif, '\n  '.join(ozet)))


def test_muafiyetlerin_her_biri_gerekceli():
    """Muafiyet listesi gerekçesiz büyümez."""
    for parca, neden in MUAF_PARCALAR.items():
        assert neden and len(neden) > 10, parca
    for rx, _baglam, neden in MUAF_KALIPLAR:
        assert neden and len(neden) > 10, rx.pattern


def test_siniflandirici_bilinen_sizintilari_yakalar():
    """Kural kendi kendine sınanır (ekran ölçümünden bağımsız)."""
    havuz = {
        "'expansion_ratio' alanı (0) formdan okunmaz": 'a',
        'the value is not computed for this case': 'b',
        'kaynak: hrma/analysis/two_phase_loss.py': 'c',
        'İtki katsayısı C_F (p_a = p_e)': 'd',          # formül: muaf
        'HRMA v3.0.1': 'e',                               # sürüm: muaf
    }
    b = siniflandir(havuz)
    assert "'expansion_ratio' alanı (0) formdan okunmaz" in b['ham_anahtar']
    assert 'İtki katsayısı C_F (p_a = p_e)' not in b['ham_anahtar']
    assert 'HRMA v3.0.1' not in b['ham_anahtar']
    assert list(b['ingilizce']) == ['the value is not computed for this case']
    assert 'kaynak: hrma/analysis/two_phase_loss.py' in b['kod']
