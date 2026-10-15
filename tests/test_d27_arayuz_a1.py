# -*- coding: utf-8 -*-
"""ÖH Dalga-27 / arayuz aşama-1 bekçisi — **P11B1-09 kalan yarısı + OH-D26-02**.

Kalem (çift kimlik, tek kusur): *3B sahnenin birincil ölçüleri çözücüden
gelmediğinde uydurma bir sabite düşüyor.*

ÖLÇÜLDÜ (``docs/scofield/raw/OH/D27/arayuz/a1/once.json``, taban ağacı):
uydurma yedek **12 sitede** duruyordu ve **üç katmana** yayılmıştı —

* sahne (``motor_viz3d.js::extractDims``): ``num(md.chamber_diameter, 0.1)``,
  ``num(md.chamber_length, 0.3)``, ``num(md.throat_diameter, 0.02)``,
  ``num(md.exit_diameter, 0.08)``;
* katı sayfası adaptörü (``solid.html::buildSolidVizData``): aynı dört sayı
  ``firstNum(…, 0.1 / 0.3 / 0.02 / 0.08)`` kuyruklarında;
* sıvı sayfası adaptörü (``liquid.html::buildLiquidVizData``):
  ``num(results.chamber_diameter, 100)`` ailesi (100/300 mm, 0,05/0,15 m).

Node altında ÖLÇÜLDÜ (``davranis_node``): çıplak bir çözücü yanıtında iki
adaptör de dördünü de uyduruyor, yani ekranda **100 mm × 300 mm'lik**,
ölçekli, ölçülü, gerçekmiş gibi duran bir motor çiziliyordu.

D26 bu düşüşü yalnız **beyan** etti (``srcDecl`` defteri + amber çip) —
beyan çözüm değildir (doktrin 1). D27'de kural fail-closed'a çevrildi:
ölçü yoksa sahne **çizilmez** ve eksik alan **adıyla** reddedilir. Sonra:
uydurma yedek **0**, kapı ``mount``/``update`` ürün yollarına bağlı.

Bu dosya iddiaları ÜRÜN KODU üstünde ölçer: metin araması yalnız
"kanal var kapı yok" ailesindeki bağlama iddiaları içindir; hükmün
kendisi ``motor_viz3d.js``in TAMAMI ve iki sayfa adaptörü node altında
GERÇEKTEN koşturularak sınanır.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = REPO_ROOT / 'hrma' / 'static' / 'js'
VIZ_JS = JS / 'motor_viz3d.js'
I18N_JS = JS / 'i18n_common.js'
SOLID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'solid.html'
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadı')

#: Ölçüm betiği — bekçi kendi ölçütünü yeniden yazmaz, ONU çağırır.
OLCUM = (REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D27' / 'arayuz'
         / 'a1' / 'olcum.py')
ONCE = OLCUM.parent / 'once.json'

#: Sahnenin çizmek için zorunlu gördüğü dört ölçü.
BIRINCIL = ('chamber_diameter', 'chamber_length',
            'throat_diameter', 'exit_diameter')


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _olcum_modulu():
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location('d27_arayuz_olcum', kanit_gerekli(OLCUM))
    mod = importlib.util.module_from_spec(spec)
    sys.argv = ['olcum.py', str(REPO_ROOT)]
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def sonuc():
    return _olcum_modulu().SONUC


@pytest.fixture(scope='module')
def taban():
    """Taban ağacının ölçümü — 'önce' sayıları (kanıt dizininde)."""
    if not kanit_gerekli(ONCE).exists():
        pytest.skip('once.json yok')
    return json.loads(kanit_gerekli(ONCE).read_text(encoding='utf-8'))


def _node(script, argv=()):
    res = subprocess.run([NODE] + ['-'] + list(argv), input=script,
                         capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


def _sabit_dize(src, ad):
    """``var AD = '…';`` bildirimini ÜRÜN kaynağından aynen çıkarır."""
    m = re.search(r"var %s = '[^']*';" % re.escape(ad), src)
    assert m, 'sabit bulunamadı: %s' % ad
    return m.group(0)


def _govde(src, ad):
    """``function ad(`` ya da ``ad: function`` gövdesini çıkarır."""
    k = src.find('function %s(' % ad)
    if k < 0:
        k = src.find('%s: function' % ad)
    assert k >= 0, 'bulunamadı: %s' % ad
    derinlik, i, basladi = 0, k, False
    while i < len(src):
        if src[i] == '{':
            derinlik += 1
            basladi = True
        elif src[i] == '}':
            derinlik -= 1
            if basladi and derinlik == 0:
                return src[k:i + 1]
        i += 1
    raise AssertionError('%s kapanmıyor' % ad)


#: Sahte DOM — sahne modülünün KENDİSİ (kırpılmış kopyası değil) yüklenir.
#: THREE hiç tanımlanmaz: kapı ``new MotorScene``ten ÖNCE ateşlenmek
#: zorunda olduğu için reddedilen yolda Three.js'e hiç ihtiyaç olmamalıdır.
DOM_ONSOZ = r"""
'use strict';
function makeNode(id) {
    return {
        id: id, __html: '', textContent: '', style: { cssText: '' },
        attrs: {}, children: [], className: '',
        classList: { contains: function () { return false; },
                     add: function () {}, remove: function () {},
                     toggle: function () {} },
        setAttribute: function (k, v) { this.attrs[k] = String(v); },
        getAttribute: function (k) {
            return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild: function (c) { this.children.push(c); return c; },
        removeChild: function (c) { return c; },
        querySelector: function () { return null; },
        querySelectorAll: function () { return []; },
        addEventListener: function () {},
        get innerHTML() { return this.__html; },
        set innerHTML(v) { this.__html = v; this.children = []; }
    };
}
function deepText(n) {
    if (!n) return '';
    var s = String(n.textContent || '');
    (n.children || []).forEach(function (c) { s += ' ' + deepText(c); });
    return s;
}
function alanlariTopla(n, out) {
    out = out || [];
    if (!n) return out;
    var f = n.getAttribute && n.getAttribute('data-field');
    if (f) out.push(f);
    (n.children || []).forEach(function (c) { alanlariTopla(c, out); });
    return out;
}
var nodes = {};
global.document = {
    getElementById: function (id) {
        if (!(id in nodes)) nodes[id] = makeNode(id);
        return nodes[id];
    },
    createElement: function () { return makeNode(null); },
    addEventListener: function () {},
    head: makeNode('head'), body: makeNode('body')
};
global.window = global;
global.requestAnimationFrame = function () { return 1; };
require(%(viz)s);
"""


def _viz_node(govde):
    onsoz = DOM_ONSOZ % {'viz': json.dumps(str(VIZ_JS))}
    return _node(onsoz + govde)


def _adaptor_onsoz():
    """İki sayfa adaptörünün ÜRÜN gövdesi (kopya değil, dosyadan)."""
    return (_govde(SOLID_HTML.read_text(encoding='utf-8'),
                   'buildSolidVizData') + '\n'
            + _govde(LIQUID_HTML.read_text(encoding='utf-8'),
                     'buildLiquidVizData') + '\n'
            + 'function T(k, f) { return f; }\n')


# ===========================================================================
# Sahne — birincil ölçü kapısı
# ===========================================================================

class TestBirincilOlcuKapisi:
    """Ölçü yoksa sahne çizilmez; eksik alan ADIYLA reddedilir."""

    def test_uydurma_yedekler_sokuldu(self, sonuc, taban):
        """Üç katmanda da uydurma ölçü kalmadı (12 → 0)."""
        assert taban['toplam_uydurma_birincil_olcu'] == 12, (
            'taban ölçümü bayat: uydurma yedek sayısı beklenen 12 değil')
        assert taban['sahne']['uydurma_yedekli_birincil_olcu_sayisi'] == 4
        assert taban['adaptor_kati']['uydurma_birincil_olcu'] == 4
        assert taban['adaptor_sivi']['uydurma_birincil_olcu'] == 4
        assert sonuc['toplam_uydurma_birincil_olcu'] == 0, (
            sonuc['sahne']['uydurma_yedekli_birincil_olcu'],
            sonuc['adaptor_kati']['ornekler'],
            sonuc['adaptor_sivi']['ornekler'])

    def test_kapi_urun_yoluna_bagli(self, sonuc, taban):
        """KANAL VAR KAPI YOK BEKÇİSİ.

        Kapıyı yazmak yetmez: ``mount`` ve ``update`` onu çağırmazsa
        uydurma yedek sökülmüş ama sahne yine de çizilmiş olur (bu kez
        ``NaN`` geometriyle, ki daha da kötüsüdür).
        """
        for alan in ('birincil_olcu_tablosu', 'eksik_olcu_fonksiyonu',
                     'mount_kapiya_bagli', 'update_kapiya_bagli',
                     'red_dom_yaziyor', 'red_disa_verili',
                     'red_alani_adiyla_beyan',
                     'extract_dims_kapiyi_cagiriyor'):
            assert taban['sahne'][alan] == 0, alan
            assert sonuc['sahne'][alan] >= 1, alan

    def test_extract_dims_birincil_olcuyu_uydurmuyor(self, sonuc):
        """``extractDims`` gövdesinde sayısal yedek kalmadı."""
        assert sonuc['sahne']['extract_dims_birincil_yedek'] == 0

    def test_kapi_sahne_kurulmadan_once_atesleniyor(self):
        """Sıra bekçisi: ``missingPrimaryDims`` ``new MotorScene``ten ÖNCE.

        Sonra çağrılsaydı sahne uydurma/NaN ölçülerle zaten kurulmuş olurdu.
        """
        src = VIZ_JS.read_text(encoding='utf-8')
        mount = _govde(src, 'mount')
        i_kapi = mount.find('missingPrimaryDims')
        i_sahne = mount.find('new MotorScene')
        assert i_kapi >= 0 and i_sahne >= 0, mount[:400]
        assert i_kapi < i_sahne, 'kapı sahne kurulduktan SONRA sınanıyor'

    def test_mount_eksik_olcude_sahne_kurmuyor(self):
        """ÜRÜN KOŞUMU: modül node altında yüklenir, ``mount`` çağrılır.

        Beklenen: ``null`` döner, kapsayıcıya gerekçe kutusu yazılır,
        ``getDimsReject()`` eksik alanları adıyla bildirir ve Three.js'e
        hiç dokunulmaz (THREE tanımlı bile değil).
        """
        ciz = _viz_node(r"""
var out = {};
var kap = document.getElementById('vp');
try {
    out.donen = window.MotorViz3D.mount('vp', { chamber_diameter: 0.1 });
} catch (e) { out.hata = String(e && e.message); }
out.red = window.MotorViz3D.getDimsReject();
out.kutuSayisi = kap.children.length;
out.metin = deepText(kap.children[0] || null);
out.dataMissing = kap.children[0]
    ? kap.children[0].getAttribute('data-missing') : null;
out.alanlar = alanlariTopla(kap.children[0] || null);
out.sahneVar = !!window.MotorViz3D.get();
process.stdout.write(JSON.stringify(out));
""")
        assert 'hata' not in ciz, ciz.get('hata')
        assert ciz['donen'] is None, 'eksik ölçüde sahne kuruldu'
        assert ciz['sahneVar'] is False, 'reddedilen koşuda sahne asılı kaldı'
        assert ciz['red'] and ciz['red']['code'] == 'missing_primary_dims'
        assert ciz['red']['missing'] == ['chamber_length', 'throat_diameter',
                                         'exit_diameter'], ciz['red']
        assert ciz['kutuSayisi'] == 1, 'gerekçe kutusu yazılmadı'

    def test_red_eksik_alani_adiyla_soyluyor(self):
        """Sessiz boş kutu / "bir hata oluştu" YASAK: alan ADIYLA yazılır."""
        ciz = _viz_node(r"""
var kap = document.getElementById('vp');
window.MotorViz3D.mount('vp', {});
var kutu = kap.children[0];
process.stdout.write(JSON.stringify({
    metin: deepText(kutu), alanlar: alanlariTopla(kutu),
    dataMissing: kutu.getAttribute('data-missing')
}));
""")
        assert sorted(ciz['alanlar']) == sorted(BIRINCIL), ciz['alanlar']
        assert ciz['dataMissing'] == ','.join(BIRINCIL)
        for alan in BIRINCIL:
            assert alan in ciz['metin'], (alan, ciz['metin'])
        # Okunur etiket de var: kullanıcı alan adını ezberlemek zorunda değil.
        for etiket in ('chamber', 'throat', 'exit'):
            assert etiket in ciz['metin'].lower(), etiket

    def test_hukum_sifir_negatif_ve_sayi_olmayani_reddediyor(self):
        """Ölçü "var" demek yetmez: 0 / negatif / dize geçerli ölçü değildir."""
        ciz = _viz_node(r"""
var M = window.MotorViz3D.missingPrimaryDims;
var tam = { chamber_diameter: 0.1, chamber_length: 0.3,
            throat_diameter: 0.02, exit_diameter: 0.08 };
function kopya(yama) {
    var o = {};
    Object.keys(tam).forEach(function (k) { o[k] = tam[k]; });
    Object.keys(yama).forEach(function (k) { o[k] = yama[k]; });
    return o;
}
process.stdout.write(JSON.stringify({
    tam: M(tam),
    bos: M({}),
    yok: M(kopya({ throat_diameter: undefined })),
    sifir: M(kopya({ chamber_length: 0 })),
    negatif: M(kopya({ exit_diameter: -0.08 })),
    dize: M(kopya({ chamber_diameter: '0.1' })),
    nan: M(kopya({ chamber_diameter: NaN })),
    sonsuz: M(kopya({ chamber_length: Infinity })),
    hicbiri: M(null)
}));
""")
        assert ciz['tam'] == []
        assert ciz['bos'] == list(BIRINCIL)
        assert ciz['hicbiri'] == list(BIRINCIL)
        assert ciz['yok'] == ['throat_diameter']
        assert ciz['sifir'] == ['chamber_length'], 'sıfır ölçü geçerli sayıldı'
        assert ciz['negatif'] == ['exit_diameter']
        assert ciz['dize'] == ['chamber_diameter'], 'dize sayı sayıldı'
        assert ciz['nan'] == ['chamber_diameter']
        assert ciz['sonsuz'] == ['chamber_length']

    def test_extract_dims_dogrudan_cagrilirsa_da_uydurmuyor(self):
        """İKİNCİ SAVUNMA: kapıyı atlayan yeni bir yol açılırsa
        ``extractDims`` sessizce uydurma geometri üretmez, ALAN ADIYLA
        hüküm fırlatır."""
        src = VIZ_JS.read_text(encoding='utf-8')
        prelude = ('function num(v, f) { '
                   'return (typeof v === "number" && isFinite(v)) ? v : f; }\n'
                   + _govde(src, 'missingPrimaryDims') + '\n'
                   + _govde(src, 'MotorDimsError') + '\n'
                   + 'MotorDimsError.prototype = Object.create(Error.prototype);\n'
                   + 'var PRIMARY_DIM_FIELDS = '
                   + json.dumps(list(BIRINCIL)) + ';\n'
                   + _sabit_dize(src, 'DIMS_REJECT_CODE') + '\n')
        # extractDims'in İLK satırları (kapı) — gövdenin tamamı THREE ister.
        ed = _govde(src, 'extractDims')
        kapi = ed[ed.index('var eksikOlcu'):ed.index('var Dch')]
        assert 'MotorDimsError' in kapi, kapi
        ciz = _node(prelude + 'function dene(md) {\n' + kapi
                    + '\n  return null;\n}\n' + r"""
var out = {};
try { out.bos = dene({}); }
catch (e) { out.bos = { ad: e.name, kod: e.code, eksik: e.missing }; }
try { out.tam = dene({ chamber_diameter: 0.1, chamber_length: 0.3,
                       throat_diameter: 0.02, exit_diameter: 0.08 }); }
catch (e) { out.tam = { ad: e.name, eksik: e.missing }; }
process.stdout.write(JSON.stringify(out));
""")
        assert ciz['tam'] is None, 'tam veri reddedildi'
        assert ciz['bos']['ad'] == 'MotorDimsError', ciz['bos']
        assert ciz['bos']['kod'] == 'missing_primary_dims'
        assert ciz['bos']['eksik'] == list(BIRINCIL)

    def test_red_kodu_tek_kaynak_ve_cfd_kanalindan_ayri(self):
        """TEK KAYNAK (doktrin 4) + KANAL AYRIMI.

        Kod dizesi ürün kodunda BİR kez yazılır (``mount`` ve ``update``
        aynı sabiti bildirir). Ayrıca CFD red tablosuyla (``CFD_REASONS``)
        kesişmez: kesişseydi iki kanal aynı kodu iki farklı anlamda
        kullanır, güverte yanlış metni basardı.
        """
        src = VIZ_JS.read_text(encoding='utf-8')
        sabit = _sabit_dize(src, 'DIMS_REJECT_CODE')
        kod = re.search(r"'([^']+)'", sabit).group(1)
        assert kod == 'missing_primary_dims', sabit
        assert src.count("'%s'" % kod) == 1, (
            'red kodu birden çok yerde yazılmış (tek kaynak ihlali)')
        cfd = src[src.index('CFD_REASONS'):]
        cfd = cfd[:cfd.index('\n    }')]
        assert kod not in cfd, 'ölçü reddi CFD red tablosuna sızmış'

    def test_i18n_anahtarlari_en_ve_tr_blogunda(self, sonuc, taban):
        """Anahtar dosya SONUNA değil, ilgili bloğun İÇİNE (D21 kuralı)."""
        assert taban['i18n_anahtar_sayilari']['_eksiksiz_cift_sayisi'] == 0
        i = sonuc['i18n_anahtar_sayilari']
        assert i['_eksiksiz_cift_sayisi'] == i['_toplam_anahtar'], i

    def test_hukum_defteri_ve_cip_kanali_korunuyor(self, sonuc):
        """D26'nın beyan defteri SÖKÜLMEDİ: kapı beyanı değiştirmez,
        yalnız uydurmayı kaldırır (cidar/tane yedekleri beyanlı kalır)."""
        src = VIZ_JS.read_text(encoding='utf-8')
        ed = _govde(src, 'extractDims')
        for alan in BIRINCIL + ('grain_length',):
            assert "decl('%s'" % alan in ed, alan
        assert 'srcDecl: srcDecl' in ed
        assert 'dimensionSourceChipDefs' in src


# ===========================================================================
# Sayfa adaptörleri — uydurma bir katman ÖNCE olmasın
# ===========================================================================

class TestSayfaAdaptorleri:
    """Kapı ancak adaptör de uydurmayı bırakırsa ateşlenebilir."""

    def test_ciplak_yanitta_olcu_uydurulmuyor(self, sonuc, taban):
        """Çıplak çözücü yanıtı → hiçbir birincil ölçü üretilmez (4+4 → 0)."""
        assert taban['davranis_node']['solid_bos_uydurulan_sayi'] == 4
        assert taban['davranis_node']['liquid_bos_uydurulan_sayi'] == 4
        assert sonuc['davranis_node']['solid_bos_uydurulan_sayi'] == 0
        assert sonuc['davranis_node']['liquid_bos_uydurulan_sayi'] == 0

    def test_null_carpimi_sessiz_sifir_olcu_uretmiyor(self):
        """``null * 0.9`` sıfırdır ve sıfır SONLU bir sayıdır: yedek
        zinciri onu geçerli ölçü sanabilirdi (0 mm'lik tane / port)."""
        ciz = _node(_adaptor_onsoz() + r"""
var d = buildSolidVizData({});
process.stdout.write(JSON.stringify({
    grain_length: d.grain_length,
    port_diameter_initial: d.port_diameter_initial,
    chamber_length: d.chamber_length
}));
""")
        for alan, deger in ciz.items():
            assert deger is None or deger > 0, (alan, deger)

    def test_gercek_yanitta_olculer_cozucunun_sayilari(self):
        """FAIL-CLOSED REGRESYON BEKÇİSİ.

        Kapı doğru olsun diye ürünü kırmak serbest değildir: GERÇEK
        ``/calculate_solid`` ve ``/calculate_liquid`` yanıtlarının ölçüleri
        (docs/scofield/raw/OH/D27/arayuz/a1/capa_once.json, 8 Eylül 2026
        koşumu) adaptörden çözücünün sayısı olarak çıkmalı — dördü de.
        """
        ciz = _node(_adaptor_onsoz() + r"""
// /calculate_solid gerçek yanıtının ilgili alanları (mm)
var kati = {
    chamber_diameter: 124.76256495492507,
    throat_diameter: 32.92487210731246,
    exit_diameter: 80.18911836745107,
    grain_length: 450.31511603832615,
    core_diameter: 76.02742117355093,
    cad_design: {
        case_design: { inner_diameter: 124.76256495492507,
                       length: 550.3151160383262 },
        grain_geometry: { outer_diameter: 124.76256495492507,
                          length: 450.31511603832615,
                          core_diameter: 76.02742117355093 }
    }
};
// /calculate_liquid gerçek yanıtı: oda mm, boğaz/çıkış METRE
var sivi = {
    chamber_diameter: 112.17303406532352,
    chamber_length: 249.5504014028547,
    throat_diameter: 0.05527802111294594,
    exit_diameter: 0.12408275907762767
};
function dort(d) {
    return { chamber_diameter: d.chamber_diameter,
             chamber_length: d.chamber_length,
             throat_diameter: d.throat_diameter,
             exit_diameter: d.exit_diameter };
}
process.stdout.write(JSON.stringify({
    kati: dort(buildSolidVizData(kati)),
    sivi: dort(buildLiquidVizData(sivi))
}));
""")
        # Katı: mm → m, çözücünün sayısı birebir (kasa iç boyu = oda boyu;
        # motor_geometry.chamber_length 0,5503151160383262 ile ÇAPRAZ tutar).
        assert ciz['kati']['chamber_diameter'] == pytest.approx(0.12476256495492507)
        assert ciz['kati']['chamber_length'] == pytest.approx(0.5503151160383262)
        assert ciz['kati']['throat_diameter'] == pytest.approx(0.03292487210731246)
        assert ciz['kati']['exit_diameter'] == pytest.approx(0.08018911836745107)
        # Sıvı: oda mm→m, boğaz/çıkış zaten metre (AYNEN geçer).
        assert ciz['sivi']['chamber_diameter'] == pytest.approx(0.11217303406532352)
        assert ciz['sivi']['chamber_length'] == pytest.approx(0.2495504014028547)
        assert ciz['sivi']['throat_diameter'] == pytest.approx(0.05527802111294594)
        assert ciz['sivi']['exit_diameter'] == pytest.approx(0.12408275907762767)

    def test_gercek_yanit_kapidan_geciyor(self):
        """Aynı gerçek yanıtlar sahne kapısından da geçmeli (aksi hâlde
        onarım ürünü kapatırdı)."""
        ciz = _viz_node(r"""
var M = window.MotorViz3D.missingPrimaryDims;
process.stdout.write(JSON.stringify({
    kati: M({ chamber_diameter: 0.12476256495492507,
              chamber_length: 0.5503151160383262,
              throat_diameter: 0.03292487210731246,
              exit_diameter: 0.08018911836745107 }),
    sivi: M({ chamber_diameter: 0.11217303406532352,
              chamber_length: 0.2495504014028547,
              throat_diameter: 0.05527802111294594,
              exit_diameter: 0.12408275907762767 })
}));
""")
        assert ciz['kati'] == [] and ciz['sivi'] == []

    def test_sivi_paneli_olcu_reddini_gizlemiyor(self):
        """Fail-closed'ın SESSİZ olması yasak: sıvı sayfası güverte
        kurulmadığında paneli körü körüne gizliyordu; gerekçe kutusu o
        panelin içindedir."""
        src = LIQUID_HTML.read_text(encoding='utf-8')
        blok = _govde(src, 'generateCADVisualization')
        assert 'getDimsReject' in blok, (
            'panel gizleme kararı ölçü reddini SORMUYOR — gerekçe yutuluyor')
        gizle = blok.index("vizPanel.style.display = 'none'")
        sor = blok.index('getDimsReject')
        assert sor < gizle, 'red gizlemeden SONRA soruluyor'

    def test_adaptor_dosyalari_node_altinda_ayristirilabiliyor(self):
        """Şablon içi JS sözdizimsel olarak sağlam (gövde çıkarımıyla)."""
        onsoz = _adaptor_onsoz()
        p = pathlib.Path(os.environ.get('TMPDIR', '/tmp')) / (
            'd27_arayuz_a1_adaptor_%d.js' % os.getpid())
        p.write_text(onsoz, encoding='utf-8')
        try:
            res = subprocess.run([NODE, '--check', str(p)],
                                 capture_output=True, text=True, timeout=60)
            assert res.returncode == 0, res.stderr[-800:]
        finally:
            p.unlink(missing_ok=True)


def test_sahne_modulu_node_altinda_ayristirilabiliyor():
    res = subprocess.run([NODE, '--check', str(VIZ_JS)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr[-800:]
    res = subprocess.run([NODE, '--check', str(I18N_JS)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr[-800:]
