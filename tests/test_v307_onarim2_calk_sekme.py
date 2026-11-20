"""3.0.7 ONARIM2-ÇALK-SEKME — Çalkantı sekmesi ve 6-DOF çalkantı alt bölümü
bulgularının (mühendis turu 19 Kas, onarım dalgası 2) bekçileri.

Ne kilitlenir (sözleşme ve fizik, bugünkü çıktı değil):
  * M7-UCUS-4 (a) istemci eşi: çalkantı paneli bağlaşık koşunun yayımını
    sunucunun yayım kaydından (``calkanti.yayim.neden_kodu``) okur; iki neden
    kodundan biri geldiyse bağlaşık tüm-uçuş sayıları basılmaz, geçerlilik
    sınırı ``t_gecersiz_bas_s`` (null ise koşunun tamamı geçerlilik dışı),
    rijit koşu "çalkantısız referans koşu" etiketiyle durur, metin nedeni
    adıyla söyler. Kodlar sunucunun ``CALKANTI_YAYIM_NEDENLERI`` kümesiyle
    aynı.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
PANEL = JS / 'calkanti_panel.js'


def _sozluk_degeri(anahtar, dil):
    """i18n_common.js'te anahtarın EN (0) / TR (1) değeri."""
    metin = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    bulunan = re.findall(r"^\s*'%s': '((?:[^'\\]|\\.)*)',$" % re.escape(anahtar),
                         metin, re.M)
    assert len(bulunan) == 2, (anahtar, len(bulunan))
    return bulunan[{'en': 0, 'tr': 1}[dil]].replace("\\'", "'")


def _node(betik_metni, tmp_path):
    if shutil.which('node') is None:
        pytest.skip('node yok')
    betik = tmp_path / 'b.js'
    betik.write_text(betik_metni, encoding='utf-8')
    p = subprocess.run([shutil.which('node'), str(betik)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


#: Panelin DOM'suz çizimi: 6-DOF çalkantı alt bölümü (``sd_calkanti_sonuc``)
#: ve rozet şeridi (``sd_badges``) yakalanır; tablo satırları ``kv``de.
_DUZENEK = r"""
global.window = {location: {pathname: '/hybrid'}};
const eklenen = [];
const rozet = {parentNode: {insertBefore: (d) => eklenen.push(d)}};
const kok = {children: [], innerHTML: '', appendChild(d) { this.children.push(d); }};
global.document = {createElement: () => ({style: {}, appendChild() {}}),
  getElementById: (id) => (id === 'sd_badges' ? rozet : id === 'sd_calkanti_sonuc' ? kok : null)};
let kv = [];
window.AnalysisDock = {ui: {badge: (t) => t, sectionTitle: (t) => '[' + t + ']', listBlock: () => '',
  kvTable: (rows) => { kv = kv.concat(rows); return ''; }, TD: '', TBL: '',
  num: (x, d) => (d === undefined ? String(x) : x.toFixed(d))}};
require(%r);
const C = window.HRMACalkanti;
function ciz(yayim, ds) {
  eklenen.length = 0; kok.children = []; kv = [];
  const h = {genel_hukum: 'CALKANTI_KAYNAKLI_KARARSIZLIK', gerekce_kodu: 'YANMA_ICI_CALKANTI_KARARSIZLIK_PENCERESI',
    pencereler: [{t1: 3.5352, t2: 10.32, mod: 'calkanti', buyume_ussu: 1.875}], rijit_pencereler: [],
    dogrusal_sinir: ds || {asildi: false, max_eta_R: 0.0727, sinir: 0.2}};
  const y = {summary: {apogee: null, max_alpha_deg: null, static_margin_full: 2.0, static_margin_empty: 1.5},
    calkanti: {durum: 'BAGLANDI', tanklar: [], slosh_stability: h, yayim: yayim,
      rijit_karsilastirma: {apogee: 5153.9, max_alpha_deg: 3.147}}};
  C.sixdofCiz(y);
  return {html: kok.children.map((d) => d.innerHTML || '').join('\n'),
          kv: kv.map((r) => r.join(' = ')), rozet: eklenen.map((d) => d.textContent)};
}
"""

_PENCERE = {'neden_kodu': 'BAGLASIK_KOSU_KARARSIZ_PENCERE', 't_gecersiz_bas_s': 3.5352,
            't_ilk_asim_s': None, 'gecerlilik': 'KARARSIZ_PENCERE_GENLIK_TOHUMA_BAGLI'}


# ===========================================================================
# M7-UCUS-4 (a) — çalkantı paneli eşi
# ===========================================================================
class TestPencereYayimKurali:

    def test_istemci_kodlari_sunucuyla_ayni(self):
        from hrma import app as app_mod
        kaynak = PANEL.read_text(encoding='utf-8')
        istemci = re.findall(r"const YAYIM_NEDEN_(?:SINIR|PENCERE) = '([A-Z_]+)';", kaynak)
        assert tuple(istemci) == tuple(app_mod.CALKANTI_YAYIM_NEDENLERI)

    def test_yayim_durumu_iki_neden_ve_fail_closed(self, tmp_path):
        r = _node(
            "global.window = {location: {pathname: '/hybrid'}};\nglobal.document = {};\n"
            "require(%r);\nconst C = window.HRMACalkanti;\n"
            "process.stdout.write(JSON.stringify([\n"
            " C._yayimDurumu({neden_kodu: 'BAGLASIK_KOSU_KARARSIZ_PENCERE', t_gecersiz_bas_s: 3.5}, null),\n"
            " C._yayimDurumu({neden_kodu: 'BAGLASIK_KOSU_KARARSIZ_PENCERE', t_gecersiz_bas_s: null}, null),\n"
            " C._yayimDurumu({neden_kodu: 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI', t_gecersiz_bas_s: 27.93}, null),\n"
            " C._yayimDurumu({neden_kodu: null, t_gecersiz_bas_s: null}, {dogrusal_sinir: {asildi: false}}),\n"
            " C._yayimDurumu(undefined, {dogrusal_sinir: {asildi: true, t_ilk_asim_s: 27.93}}),\n"
            " C._yayimDurumu(undefined, {dogrusal_sinir: {asildi: false}})]));\n"
            % str(PANEL), tmp_path)
        assert r[0] == {'neden': 'BAGLASIK_KOSU_KARARSIZ_PENCERE', 't': 3.5}
        assert r[1] == {'neden': 'BAGLASIK_KOSU_KARARSIZ_PENCERE', 't': None}
        assert r[2] == {'neden': 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI', 't': 27.93}
        assert r[3] is None
        assert r[4] == {'neden': 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI', 't': 27.93}
        assert r[5] is None

    def test_pencere_kodunda_bagli_sayi_basilmaz_neden_adiyla(self, tmp_path):
        """ÖLÇÜLDÜ (hibrit örnek, rüzgâr 5, panelin isteği): ÖNCE apoje satırı
        'coupled run (published) / slosh-free comparison = — m / 5153.9 m' ve
        'stayed inside the linear limit' (onarim2-calk-sekme/metin)."""
        r = _node(_DUZENEK % str(PANEL)
                  + "process.stdout.write(JSON.stringify([ciz(%s), ciz(%s), ciz(%s)]));\n"
                  % (json.dumps(_PENCERE),
                     json.dumps(dict(_PENCERE, t_gecersiz_bas_s=None)),
                     json.dumps({'neden_kodu': None, 't_gecersiz_bas_s': None,
                                 'gecerlilik': 'GECERLI'})), tmp_path)
        pen, pen_null, gecerli = r
        # bağlaşık sayı satırı yok; nedenin adı ve geçerlilik sınırı var
        assert not any('coupled run (published)' in s for s in pen['kv']), pen['kv']
        satir = [s for s in pen['kv'] if s.startswith('Coupled run (with slosh)')]
        assert len(satir) == 1 and 'instability window in the burn (from t = 3.535 s)' in satir[0], pen['kv']
        assert 'depends on the initial disturbance' in satir[0]
        assert 'Slosh-free reference run' in pen['html'] and 'apogee 5153.9 m' in pen['html']
        # hüküm bölümü: "sınırın içinde kaldı" değil; tohum cümlesi gerekçe
        assert 'stayed inside the linear limit' not in pen['html']
        assert 'initial wave of η/R ≈ 0.031' in pen['html']
        assert 'set by the initial disturbance' in pen['html']
        # rozet üstü: köprü notu (marj bandı) + nedenli uyarı + referans
        assert len(pen['rozet']) == 2, pen['rozet']
        assert 'static-margin band' in pen['rozet'][0]
        assert 'from t = 3.535 s' in pen['rozet'][1] and 'apogee 5153.9 m' in pen['rozet'][1]
        # FAIL-CLOSED: sınır bilinmiyorsa koşunun tamamı geçerlilik dışı
        assert any('whole coupled run is treated as outside validity' in s for s in pen_null['kv'])
        assert 'whole coupled run' in pen_null['rozet'][1]
        # kod yoksa bugünkü yol (bağlaşık + karşılaştırma satırı)
        assert any(s.startswith('Apogee: coupled run (published) / slosh-free comparison')
                   for s in gecerli['kv']), gecerli['kv']
        assert 'stayed inside the linear limit' in gecerli['html']

    def test_sinir_asimi_eskisi_gibi(self, tmp_path):
        r = _node(_DUZENEK % str(PANEL)
                  + "process.stdout.write(JSON.stringify(ciz(%s, %s)));\n"
                  % (json.dumps({'neden_kodu': 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI',
                                 't_gecersiz_bas_s': 27.93, 't_ilk_asim_s': 27.93}),
                     json.dumps({'asildi': True, 't_ilk_asim_s': 27.93, 'sinir': 0.2,
                                 'max_eta_R_sinir_oncesi': 0.19})), tmp_path)
        assert any('passed the linear validity limit at t = 27.930 s' in s for s in r['kv'])
        assert 'passed the linear limit η/R = 0.20 at t = 27.930 s' in r['html']
        assert 'instability window (from' not in r['html']

    def test_metinler_iki_dilde(self):
        for anahtar, yer in (('panel.calkanti.hk.dogrusalPencere', ('{bas}', '{m}', '{sinir}')),
                             ('panel.calkanti.hk.dogrusalPencereSonuc', ()),
                             ('panel.calkanti.hk.anaUyariPencere', ('{bas}',)),
                             ('panel.calkanti.sd.bagliYayimlanmadiPencere', ('{bas}',)),
                             ('panel.calkanti.hk.pencereBas', ('{t}',)),
                             ('panel.calkanti.hk.pencereBasYok', ()),
                             ('panel.calkanti.hk.sonGecersizPencere', ()),
                             ('panel.calkanti.hk.gecersizKisaPencere', ())):
            for dil in ('en', 'tr'):
                m = _sozluk_degeri(anahtar, dil)
                assert all(y in m for y in yer), (anahtar, dil)
        tr = _sozluk_degeri('panel.calkanti.hk.dogrusalPencereSonuc', 'tr')
        assert 'başlangıç bozucusu' in tr and 'çalkantısız referans koşu' in tr
        assert 'yayımlanmaz' in _sozluk_degeri('panel.calkanti.sd.bagliYayimlanmadiPencere', 'tr')


# ===========================================================================
# M7-CALK-6 — reddedilen girdiden sonra eski sonuç; tek değerli aralığın
# iletisi (sunucunun asıl nedeni)
# ===========================================================================
def _ret_govdesi(g):
    """Ucun gerçek ret gövdesi (katı motor: motor sonucu gerekmez)."""
    import contextlib
    import io
    from hrma.app import app
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()):
        r = app.test_client().post('/api/slosh-analysis', json={
            'tank_modeli': {'motor_type': 'solid', 'g_eff_m_s2': g}})
    assert r.status_code == 400, r.get_json()
    return r.get_json()


_HESAP_DUZENEGI = r"""
global.window = {location: {pathname: '/liquid'}, currentResults: {x: 1}};
const el = {};
const alan = (id, v) => { el[id] = {value: v, textContent: '', innerHTML: ''}; };
alan('clk_durum', ''); alan('clk_sonuc', ''); alan('clk_yontem', '');
global.document = {getElementById: (id) => el[id] || null, createElement: () => ({style: {}})};
window.AnalysisDock = {ui: {num: (x, d) => (d === undefined ? String(x) : x.toFixed(d))}};
require(%r);
const C = window.HRMACalkanti;
const sonuclar = [];
async function dene(lo, hi, govde) {
  alan('clk_geff_min', lo); alan('clk_geff_max', hi);
  C._durumlar.sonVeri = {g_eff_m_s2: [0.1, 50]}; C._durumlar.sonIstek = {g_eff_m_s2: [0.1, 50]};
  el.clk_sonuc.innerHTML = 'ESKI SONUC';
  global.fetch = async () => ({ok: false, status: 400, json: async () => govde});
  await C._hesapla();
  sonuclar.push({durum: el.clk_durum.textContent, sonuc: el.clk_sonuc.innerHTML,
                 veri: C._durumlar.sonVeri, istek: C._durumlar.sonIstek});
}
(async () => {
  for (const [lo, hi, g] of GIRDILER) await dene(lo, hi, g);
  process.stdout.write(JSON.stringify(sonuclar));
})();
"""


class TestRetSonrasiEskiSonuc:

    def test_ret_eski_sonucu_temizler_ve_asil_nedeni_soyler(self, tmp_path):
        """ÖLÇÜLDÜ (mühendis adımı, a10): 0,1–50 hesaplandıktan sonra alt = −5,
        üst = 10 ve alt = üst = 0,001; ÖNCE ikisinde de aynı genel ileti
        ('tek bir pozitif değer ya da üst değeri büyük …') ve altında önceki
        koşunun başlığı, tabloları, aktarım düğmeleri."""
        girdiler = [['-5', '10', _ret_govdesi([-5, 10])],
                    ['0.001', '0.001', _ret_govdesi([0.001, 0.001])],
                    ['0', '', _ret_govdesi(0)],
                    ['', '7', _ret_govdesi([None, 7])]]
        # sunucunun asıl nedeni alan + kod olarak geliyor
        assert girdiler[0][2]['invalid_fields'][0]['field'] == 'g_eff_m_s2[0]'
        assert girdiler[1][2]['invalid_fields'][0]['field'] == 'g_eff_m_s2'
        assert girdiler[1][2]['invalid_fields'][0]['reason'] == 'ARALIK_DISI'
        r = _node(_HESAP_DUZENEGI.replace('GIRDILER', json.dumps(girdiler)) % str(PANEL), tmp_path)
        for k in r:
            assert k['sonuc'] == '' and k['veri'] is None and k['istek'] is None, k
            assert 'previous result was cleared' in k['durum'], k['durum']
        assert 'lower (or single)' in r[0]['durum'] and 'given: -5 m/s²' in r[0]['durum']
        assert 'equal values are not a range' in r[1]['durum']
        assert 'lower (or single)' in r[2]['durum'] and 'given: 0 m/s²' in r[2]['durum']
        assert 'without a lower one' in r[3]['durum']
        for k in r:
            assert 'give one positive value, or a lower' not in k['durum']

    def test_iletiler_iki_dilde_ve_kural_ipucuyla_ayni(self):
        tr = _sozluk_degeri('panel.calkanti.retGeffEsit', 'tr')
        assert 'eşit olamaz' in tr
        for anahtar in ('panel.calkanti.retGeffAlt', 'panel.calkanti.retGeffUst'):
            for dil in ('en', 'tr'):
                assert '{v}' in _sozluk_degeri(anahtar, dil)
        for dil in ('en', 'tr'):
            assert _sozluk_degeri('panel.calkanti.oncekiTemizlendi', dil)
            assert _sozluk_degeri('panel.calkanti.retGeffAltYok', dil)
        # ipucunun kabul kuralı (üst > alt) koddaki kuralla aynı
        assert 'greater than the lower value' in _sozluk_degeri('panel.calkanti.help.g_eff_max', 'en')
        import inspect
        from hrma.analysis import calkanti_arayuz as ca
        assert 'if not hi > lo:' in inspect.getsource(ca.geff_listesi)


# ===========================================================================
# M7-CALK-7 — aktarım dosyalarının dili ve sütun sözlüğü
# ===========================================================================
_TRK = re.compile('[çğıöşüÇĞİÖŞÜ]')


@pytest.fixture(scope='module')
def sivi_sonucu():
    from tests.test_v307_onarim_calk import _coz
    return _coz('liquid')


def _aktar(sonuc, bicim, dil=None, tank='oksitleyici'):
    import contextlib
    import io
    from hrma.app import app
    app.config['TESTING'] = True
    da = {'tank_id': tank, 'bicim': bicim}
    if dil is not None:
        da['dil'] = dil
    with contextlib.redirect_stdout(io.StringIO()):
        return app.test_client().post('/api/slosh-analysis/export', json={
            'tank_modeli': {'motor_type': 'liquid', 'motor_sonucu': sonuc},
            'disa_aktarim': da})


def _meta(metin):
    from hrma.analysis import calkanti_arayuz as ca
    satir = metin.split('\n')[1]
    assert satir.startswith(ca.CSV_META_ONEKI)
    return json.loads(satir[len(ca.CSV_META_ONEKI):])


@pytest.mark.slow
class TestAktarimDiliVeSozluk:

    def test_tr_kunye_turkce_en_kunye_ingilizce(self, sivi_sonucu):
        """ÖLÇÜLDÜ (mühendis turu): TR künyede 'Control loop not modelled; …',
        EN arayüzden inen üç dosya TR ile bayt bayt aynıydı."""
        from hrma.analysis import calkanti_arayuz as ca
        from hrma.analysis import six_dof_slosh as k2
        tr = json.loads(_aktar(sivi_sonucu, 'json', 'tr').data.decode('utf-8'))
        en_r = _aktar(sivi_sonucu, 'json', 'en')
        en = json.loads(en_r.data.decode('utf-8'))
        assert 'HRMA_slosh_liquid_oksitleyici_handoff.json' in en_r.headers['Content-Disposition']
        assert ca.KAPSAM_DISI_GEREKCE_TR in ' '.join(tr['kunye'])
        assert tr['kapsam_disi']['gerekce'] == ca.KAPSAM_DISI_GEREKCE_TR
        assert en['kapsam_disi']['gerekce'] == k2.KAPSAM_DISI_GEREKCE
        assert en['kapsam_disi']['kod'] == tr['kapsam_disi']['kod']
        assert ca.EKSEN_KURALI_EN in en['kunye'] and ca.K4_KUNYE_EN in en['kunye']
        # Bu modülün kendi satırlarında EN dosyada Türkçe harf yok (kaynak
        # modüllerin dizgeleri — m(t)/yoğunluk kaynağı — RAPOR'da AÇIK).
        kendi = [k for k in en['kunye'] if not k.startswith(('m(t):', 'Density:', 'Viscosity:'))]
        assert not [k for k in kendi if _TRK.search(k)], kendi
        # makine okur içerik iki dilde AYNI (araç ekibinin okuyucusu)
        assert en['esdeger_model_tablosu']['satirlar'] == tr['esdeger_model_tablosu']['satirlar']
        assert en['zaman_ekseni']['satirlar'] == tr['zaman_ekseni']['satirlar']
        assert en['zaman_ekseni']['birimler'] == tr['zaman_ekseni']['birimler']
        assert en['dil'] == 'en' and tr['dil'] == 'tr'

    def test_iki_csvde_birim_ve_tanim_sozlugu(self, sivi_sonucu):
        from hrma.analysis import calkanti_arayuz as ca
        from hrma.analysis import slosh_tablo as st
        for dil, bas in (('tr', 'Sütunlar (birim; tanım): '), ('en', 'Columns (unit; definition): ')):
            dol = _aktar(sivi_sonucu, 'csv_doluluk', dil).data.decode('utf-8')
            satir = [k for k in _meta(dol)['kunye'] if k.startswith(bas)]
            assert len(satir) == 1
            for c in st.SATIR_SUTUNLARI:
                assert '%s [%s]' % (c, ca.SUTUN_SOZLUGU[c][0]) in satir[0], c
            # sözleşme okuyucusundan geçer (meta nesnesi değişmedi)
            assert st.csv_oku(dol.encode('utf-8')).sozluk()['satirlar']
            zam = _meta(_aktar(sivi_sonucu, 'csv_zaman', dil).data.decode('utf-8'))
            assert set(zam['tanimlar']) == set(zam['birimler']) == {c for c, _ in ca.ZAMAN_SUTUNLARI}
        assert 'doluluk oranı' in zam['tanimlar']['doluluk'] or 'fill fraction' in zam['tanimlar']['doluluk']

    def test_varsayilan_tr_ve_bilinmeyen_dil_adli_ret(self, sivi_sonucu):
        r = _aktar(sivi_sonucu, 'csv_zaman')
        assert r.status_code == 200 and 'HRMA_calkanti_liquid_oksitleyici_zaman.csv' in r.headers['Content-Disposition']
        r = _aktar(sivi_sonucu, 'json', 'de')
        assert r.status_code == 400
        assert r.get_json()['invalid_fields'][0]['field'] == 'disa_aktarim.dil'


class TestAktarimSozlukTekAnlam:

    def test_kod_metni_en_ekranla_ayni(self):
        """Dosyadaki EN kod metni ekrandaki EN metinle aynı; her K4/K5 kodu."""
        from hrma.analysis import calkanti_arayuz as ca
        from hrma.analysis import slosh_motor_baglanti as k4
        assert set(ca.KOD_METNI_EN) == set(k4.KODLAR) | set(ca.K5_KODLARI)
        for kod, metin in ca.KOD_METNI_EN.items():
            assert _sozluk_degeri('panel.calkanti.kod.' + kod, 'en') == metin, kod

    def test_panel_dili_gonderir(self):
        kaynak = PANEL.read_text(encoding='utf-8')
        assert "dil: (window.I18N && window.I18N.lang === 'en') ? 'en' : 'tr'" in kaynak


# ===========================================================================
# M7-CALK-14 — tek tank formu: ret iletileri, çözücü cümleleri, h/R terimi
# ===========================================================================
def _feed_node(tmp_path, govde):
    if shutil.which('node') is None:
        pytest.skip('node yok')
    betik = tmp_path / 'f.js'
    betik.write_text(
        "global.window = global; global.document = {getElementById(){return null;},"
        " addEventListener(){}, readyState: 'complete'};\n"
        "require(%s); require(%s);\n" % (json.dumps(str(JS / 'analysis_dock.js')),
                                         json.dumps(str(JS / 'panels' / 'feed_panel.js')))
        + govde, encoding='utf-8')
    p = subprocess.run([shutil.which('node'), str(betik)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def _tek_tank_reddi(**alanlar):
    import contextlib
    import io
    from hrma.app import app
    app.config['TESTING'] = True
    govde = {'radius': 0.2, 'fill_height': 0.5, 'g_eff': 9.81, 'fluid_density': 1141.0}
    govde.update(alanlar)
    with contextlib.redirect_stdout(io.StringIO()):
        r = app.test_client().post('/api/slosh-analysis', json=govde)
    assert r.status_code == 400
    return r.get_json()


class TestTekTankFormu:

    def test_sunucu_gerekcesi_alana_gore(self):
        """ÖLÇÜLDÜ: eksenel ivme 0 → '… would publish a negative liquid
        mass' (ivme sıvı kütlesine girmez)."""
        g = _tek_tank_reddi(g_eff=0)
        assert g['invalid_fields'][0]['field'] == 'g_eff'
        assert g['invalid_fields'][0]['reason'] == 'not_positive'
        assert 'negative liquid mass' not in g['error']
        assert 'restores the liquid surface' in g['error']
        h = _tek_tank_reddi(fill_height=0)
        assert 'negative liquid mass' not in h['error'] and 'no liquid' in h['error']
        d = _tek_tank_reddi(fluid_density=-5)
        assert 'negative liquid mass' in d['error']

    def test_ret_iletisi_alan_etiketi_ve_dogru_gerekce(self, tmp_path):
        govdeler = [_tek_tank_reddi(fill_height=0), _tek_tank_reddi(g_eff=0)]
        o = _feed_node(tmp_path,
                       "window.I18N = {lang: 'tr', t: (k, f) => 'T[' + k + ']',"
                       " tf: (k, p, f) => k + '|' + JSON.stringify(p), serverText: (x) => x};\n"
                       "const t = window.FeedPanel._tabs.filter(x => x.key === 'slosh')[0];\n"
                       "const G = %s;\n"
                       "process.stdout.write(JSON.stringify(G.map((g) => window.FeedPanel._retMetni(t, g, 400))));\n"
                       % json.dumps(govdeler))
        h, g = o
        assert h.startswith('panel.feed.slosh.retPozitif|'), h
        assert 'T[panel.feed.fFillHeight]' in h and 'T[panel.feed.slosh.retNeden.fill_height]' in h
        assert g.startswith('panel.feed.slosh.retPozitif|'), g
        assert 'T[panel.feed.fAxialAccel]' in g and 'T[panel.feed.slosh.retNeden.g_eff]' in g
        for x in o:
            assert 'must be positive' not in x and 'negative liquid mass' not in x
        for anahtar in ('panel.feed.slosh.retPozitif', 'panel.feed.slosh.retNeden.g_eff',
                        'panel.feed.slosh.retNeden.fill_height', 'panel.feed.slosh.retSonlu',
                        'panel.feed.slosh.retSayi', 'panel.feed.slosh.retNedenGenel'):
            for dil in ('en', 'tr'):
                assert _sozluk_degeri(anahtar, dil)
        assert 'kütle' not in _sozluk_degeri('panel.feed.slosh.retNeden.g_eff', 'tr')

    def test_cozucu_cumleleri_sozlukte_ve_sunucuyla_ayni(self, tmp_path):
        import inspect
        from hrma.analysis import slosh_analysis as sa
        kaynak = (JS / 'panels' / 'feed_panel.js').read_text(encoding='utf-8')
        en_not = _sozluk_degeri('panel.feed.slosh.modelNotu', 'en')
        en_zarf = _sozluk_degeri('panel.feed.slosh.zarfDayanagi', 'en')
        assert en_zarf == sa.SLOSH_SIZE_ENVELOPE_BASIS
        assert en_not.replace(' ', '') in inspect.getsource(sa.CylindricalTankSlosh).replace('"', '').replace(' ', '').replace('\n', '')
        assert "const SLOSH_MODEL_NOTU_EN = '%s';" % en_not in kaynak
        o = _feed_node(tmp_path,
                       "window.I18N = {lang: 'tr', t: (k, f) => 'T[' + k + ']',"
                       " tf: (k, p, f) => k, serverText: (x) => x};\n"
                       "window.Plotly = undefined;\n"
                       "const kok = {innerHTML: '', children: [], appendChild(d) { this.children.push(d); }};\n"
                       "global.document.createElement = () => ({style: {}, innerHTML: ''});\n"
                       "window.FeedPanel._renderSlosh({slosh: {model_note: %s, size_envelope: {basis: %s},"
                       " f1_hz: 1, fill_ratio: 1}}, kok);\n"
                       "process.stdout.write(JSON.stringify(kok.children.map((d) => d.innerHTML).join('')));\n"
                       % (json.dumps(en_not), json.dumps(en_zarf)))
        assert 'T[panel.feed.slosh.modelNotu]' in o and 'T[panel.feed.slosh.zarfDayanagi]' in o
        assert 'untranslated' not in o and 'panel.feed.proseUntranslated' not in o

    def test_h_bolu_R_adiyla_ayrilir(self):
        tr = _sozluk_degeri('panel.feed.cardFill', 'tr')
        assert 'DOLULUK' not in tr and 'h/R' in tr
        assert 'Doluluk' not in _sozluk_degeri('panel.feed.axisFill', 'tr')
        assert 'FILL' not in _sozluk_degeri('panel.feed.cardFill', 'en')


# ===========================================================================
# M7-CALK-16 — sekmenin perde önerisi 6-DOF'un gereken sönümüne bağlanır
# ===========================================================================
class TestPerdeHedefi6dof:

    def test_sekme_6dof_zeta_min_ve_onerisini_adiyla_yazar(self, tmp_path):
        """ÖLÇÜLDÜ (sıvı örnek, rüzgâr 0, panelin isteği): 6-DOF ζ_min
        0,03054, oksitleyici w/R 0,200, 10 halka; sekme ζ 0,01 tek halka.
        ÖNCE sekmede 6-DOF'a hiçbir bağ yoktu."""
        b = {'zeta_hedef': 0.03063, 'nominal': {'tanklar': [
            {'tank_id': 'oksitleyici', 'oneri': {'width_ratio': 0.201, 'halka_sayisi': 10,
                                                 'spacing_m': 0.0772}},
            {'tank_id': 'yakit', 'oneri': None, 'sebep': 'X'}]}}
        r = _node(
            "global.window = {location: {pathname: '/liquid'}, AnalysisDock: {ui: {"
            " num: (x, d) => (d === undefined ? String(x) : x.toFixed(d))}}};\nglobal.document = {};\n"
            "require(%r);\nconst C = window.HRMACalkanti;\nconst r = [];\n"
            "r.push(C._altiDofHedefMetni('oksitleyici', 0.01));\n"
            "C._sd.veri = {calkanti: {slosh_stability: {genel_hukum: 'KARARLI', bafl_onerisi: null}}};\n"
            "r.push(C._altiDofHedefMetni('oksitleyici', 0.01));\n"
            "C._sd.veri = {calkanti: {slosh_stability: {bafl_onerisi: %s}}};\n"
            "r.push(C._altiDofHedefMetni('oksitleyici', 0.01));\n"
            "r.push(C._altiDofHedefMetni('yakit', 0.01));\n"
            "r.push(C._altiDofHedefMetni('oksitleyici', 0.05));\n"
            "process.stdout.write(JSON.stringify(r));\n" % (str(PANEL), json.dumps(b)), tmp_path)
        yok, gerekmez, oks, yak, yeter = r
        assert 'HRMA default' in yok and 'No 6-DOF run' in yok
        assert 'no required damping' in gerekmez
        assert 'requires ζ_min = 0.03063' in oks and 'w/R 0.201, 10 ring' in oks
        assert 'does NOT reach it' in oks
        assert 'no design for this tank' in yak
        assert 'not below that requirement' in yeter
        for anahtar in ('panel.calkanti.bHedef6dof', 'panel.calkanti.bHedef6dofOneri',
                        'panel.calkanti.bHedef6dofYok', 'panel.calkanti.bHedef6dofYetmez'):
            for dil in ('en', 'tr'):
                assert _sozluk_degeri(anahtar, dil)
        kaynak = PANEL.read_text(encoding='utf-8')
        assert 'data-clk-6dof-hedef' in kaynak and 'altiDofHedefleriniYaz();' in kaynak

    @pytest.mark.slow
    def test_aktarim_hangi_hedefin_kullanildigini_yazar(self, sivi_sonucu):
        from hrma.analysis import calkanti_arayuz as ca
        for dil, parca in (('tr', '6-DOF kararlılık taramasının gereken ζ_min'),
                           ('en', 'NOT the ζ_min the 6-DOF stability scan requires')):
            p = json.loads(_aktar(sivi_sonucu, 'json', dil).data.decode('utf-8'))
            assert p['bafl_onerisi']['hedef_sonum_kaynagi'] == ca.BAFL_HEDEF_KAYNAGI
            assert any(parca in k for k in p['kunye']), p['kunye']
        assert any('ζ = 0,01' in k for k in json.loads(
            _aktar(sivi_sonucu, 'json', 'tr').data.decode('utf-8'))['kunye'])


# ===========================================================================
# M7-CALK-3 — katlanır bölüm rozeti: tabloda karakter değil veri satırı
# ===========================================================================
_ROZET_HARNESS = r"""
yukle('analysis_dock.js');
const body = new El('body');
function katli(ad, satir, metin) {
    const det = new El('details');
    const sum = new El('summary'); sum.textContent = ad; det.appendChild(sum);
    const govde = new El('div');
    if (satir) {
        const tablo = new El('table');
        const bas = new El('tr'); const th = new El('th'); th.textContent = 'doluluk'; bas.appendChild(th);
        tablo.appendChild(bas);
        for (let i = 0; i < satir; i++) {
            const tr = new El('tr'); const td = new El('td'); td.textContent = 'x'.repeat(80); tr.appendChild(td);
            tablo.appendChild(tr);
        }
        govde.appendChild(tablo);
    } else { govde.textContent = metin; }
    det.appendChild(govde); body.appendChild(det);
}
katli('Eşdeğer model tablosu (29 doluluk satırı)', 29, null);
katli('düz metin', 0, 'y'.repeat(1148));
sandbox.window.AnalysisDock.ui.markDeclarationFolds(body);
console.log(JSON.stringify(body.querySelectorAll('details').map(function (d) {
    return d.querySelector('summary').querySelector('[data-hd-declfold-slot]').textContent; })));
"""


class TestKatliRozetSatir:

    def test_tablo_katlisi_satir_sayisi_gosterir(self, tmp_path):
        """ÖLÇÜLDÜ (mühendis turu): 'Eşdeğer model tablosu (29 doluluk
        satırı; …)▸ 2541 karakter'."""
        from tests.test_z5_rozet_dock import NODE, node_kos
        if NODE is None:
            pytest.skip('node yok')
        r = node_kos(tmp_path, _ROZET_HARNESS)
        assert r[0] == '▸ 29 rows', r
        assert 'chars' not in r[0] and '2' not in r[0].replace('29', '')
        assert r[1] == '▸ 1148 chars', r      # tablosuz metin duvarı: eski ölçü
        for dil, m in (('en', '{n} rows'), ('tr', '{n} satır')):
            assert _sozluk_degeri('dock.foldRows', dil) == m


# ===========================================================================
# M7-CALK-4 — aynı büyüklük tek biçim
# ===========================================================================
class TestTekBicim:

    def test_viskozite_her_sivida_ayni_bicim(self, tmp_path):
        """ÖLÇÜLDÜ (mühendis turu): LOX '1,706e-7 m²/s' ⟷ RP-1
        '0,000001472 m²/s' (aynı satır başlığı)."""
        r = _node(
            "global.window = {location: {pathname: '/liquid'}, AnalysisDock: {ui: {"
            " num: (x, d) => (d === undefined ? String(x) : x.toFixed(d))}}};\nglobal.document = {};\n"
            "require(%r);\nconst C = window.HRMACalkanti;\n"
            "process.stdout.write(JSON.stringify([C._nb(1.7060e-7, 4), C._nb(1.4720e-6, 4), C._nb(2.5e-5, 4)]));\n"
            % str(PANEL), tmp_path)
        assert r == ['1.706e-7', '1.472e-6', '2.500e-5']
        kaynak = PANEL.read_text(encoding='utf-8')
        assert 'nb(t.nu_m2_s, 4)' in kaynak and 'ns(t.nu_m2_s, 4)' not in kaynak

    def test_perde_sonumu_iki_yerde_ayni_kural(self, tmp_path):
        """ÖLÇÜLDÜ: tek tank formu 'Halka perde sönüm oranı 0,0008' ⟷ Çalkantı
        bölümü 'Motorun kendi halka perde sönümü, tam dolulukta 0,00085'."""
        kaynak = PANEL.read_text(encoding='utf-8')
        assert 'ns(t.motor_bafl_sonumu_tam_doluluk, 3)' in kaynak
        o = _feed_node(tmp_path,
                       "window.I18N = {lang: 'en', t: (k, f) => f, tf: (k, p, f) => f.replace(/\\{(\\w+)\\}/g, (a, b) => p[b]),"
                       " serverText: (x) => x};\n"
                       "const kok = {innerHTML: '', children: [], appendChild(d) { this.children.push(d); }};\n"
                       "global.document.createElement = () => ({style: {}, innerHTML: ''});\n"
                       "window.FeedPanel._renderSlosh({slosh: {f1_hz: 1, fill_ratio: 1, baffle: {damping_ratio: 0.00085,"
                       " damping_ratio_low: 0.000425, damping_ratio_high: 0.0017, blocked_area_ratio: 0.1}}}, kok);\n"
                       "process.stdout.write(JSON.stringify(kok.children.map((d) => d.innerHTML).join('')));\n")
        assert '0.00085 (band 0.000425-0.0017)' in o, o[o.find('band') - 40:o.find('band') + 40]
