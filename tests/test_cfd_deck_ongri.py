"""Güvertede CFD metrik düğmelerinin ÖN-GRİSİ — ölçüm sahneden gelir.

NEDEN VAR (ölçülmüş kusur, 2026-08-18)
--------------------------------------
Sahne ``getCfdField()`` ile yüklü alanın metriğini, aralığını, hücre ve
istasyon sayısını yayımlıyordu ama **hangi büyüklüklerin yükte bulunduğunu**
yayımlamıyordu. Güverte (``motor_viz_deck.js``) bu yüzden bir metriğin yükte
olmadığını ancak KULLANICI düğmeye BASIP sahneden ``missing_metric`` reddini
yedikten sonra öğrenebiliyordu: açık duran düğme tıklanınca hiçbir şey
göstermiyor, yalnız durum satırına red yazılıyordu.

Ölçülen gerçek: ucun yayımladığı alan bloğu her zaman üç büyüklüğün
üçünü de taşımıyor — bu deponun kendi yük kurucusu
(``tests/test_viz3d_cfd_alan._yuk_kur``, ucun ``_cfd_build_grid``
sözleşmesinin aynası) ``mach`` + ``pressure_Pa`` üretiyor, ``temperature_K``
üretmiyor. Yani "üç düğme de açık" hâli yükün gerçeğiyle uyuşmuyordu.

NE KİLİTLENİR
-------------
a) SAHNE tarafı: ``getCfdField().metrics`` listesi ÖLÇÜMDÜR — süzgeç
   ``cfdFieldHasMetric``'in KENDİSİDİR (``_cfdApplyMetric``'in
   ``missing_metric`` kapısıyla tek kaynak). Yükten bir dizi silinirse
   listeden düşer, yüke eklenirse listeye girer; sabit/varsayılan liste yok.
b) GÜVERTE tarafı: ön-gri kararı bu listeden okunur (güvertede süzgecin
   kopyası YOK), karar TIKLAMADAN ÖNCE verilir ve liste sonradan değişirse
   (Merkez yeni bir alan bindirdiğinde) grup kendiliğinden tazelenir —
   yani ``cfdStateSig`` imzası metrik listesini içerir.
c) Tıklama ölçümü (``cfdMissing``) KALDIRILMADI: liste yayımlanmasa bile
   koşum reddi düğmeyi kapatır; iki ölçüm BİRLEŞİMdir.

ÖLÇÜM YÖNTEMİ
-------------
Sahne tarafı: ``motor_viz3d.js``'in GERÇEK ``getCfdField`` gövdesi ve GERÇEK
``cfdFieldHasMetric`` fonksiyonu kaynaktan çıkarılıp node'da koşturulur
(Python kopyası yok); yük GERÇEK kurucudan gelir. Güverte tarafı:
``tests/test_cfd_alan_koprusu.py``'nin GERÇEK güverte koşum düzeneği
(``kos_guverte``) ithal edilir — ikinci bir düzenek YAZILMAZ, yoksa
sözleşme sürüklenir. Betikler node'a stdin ile verilir
(``tests/test_node_cagri_sozlesmesi.py`` bekçisi).

Koşum hedeflidir (süit disiplini):
    python3 -m pytest tests/test_cfd_deck_ongri.py -q
"""

import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Koşucular/çıkarıcılar KOPYALANMAZ, ithal edilir (tek kaynak).
from tests.test_viz3d_cfd_alan import (  # noqa: E402
    _consts, _emit, _extract, _extract_method, _source, _yuk_kur,
)
from tests.test_cfd_alan_koprusu import (  # noqa: E402
    DECK_JS, _oku, kos_guverte, strip_js_comments,
)

#: Bu deponun GERÇEK yük kurucusunun ürettiği büyüklükler (ölçülen gerçek:
#: temperature_K yok). Liste burada SABİT DEĞİL, aşağıdaki testler yükün
#: kendisinden ölçüyor; bu sabit yalnız beklentiyi adlandırır.
YUK_KURUCU_METRIKLERI = ['mach', 'pressure']


# ---------------------------------------------------------------------------
# a) SAHNE — metrics listesi cfdFieldHasMetric ÖLÇÜMÜDÜR
# ---------------------------------------------------------------------------

def _sahne_prelude():
    """GERÇEK getCfdField gövdesi + GERÇEK süzgeç + GERÇEK metrik tablosu."""
    return '\n'.join([
        'var MotorScene = function () {};',
        _consts('CFD_METRICS'),
        _extract('cfdFieldHasMetric'),
        _extract_method('getCfdField') + ';',
        # Katman sözlüğü _cfdBuildLayer'ın döndürdüğü alanların
        # getCfdField tarafından OKUNAN altkümesidir
        'function beyan(field) {',
        '    var s = new MotorScene();',
        '    s._cfdLayer = { field: field, metric: "mach",',
        '        range: { min: 0.1, max: 2.9 }, nAx: 60, nRad: 12,',
        '        stationsShown: 60, stationsTotal: 60, decimated: false };',
        '    return s.getCfdField();',
        '}',
    ])


def _beyan(field):
    """Sahnenin bu yük için yayımladığı getCfdField sözlüğü."""
    return _emit(_sahne_prelude(), 'beyan(%s)' % json.dumps(field))


@pytest.fixture(scope='module')
def gercek_alan():
    """Gerçek kontur + gerçek ızgara ile kurulmuş alan bloğu (coarse)."""
    cfd, _dims, _ham = _yuk_kur('konik', 60, 12)
    return cfd['field']


class TestSahneBeyani:

    def test_metrikler_yukten_olculuyor(self, gercek_alan):
        st = _beyan(gercek_alan)
        assert st['metrics'] == YUK_KURUCU_METRIKLERI, (
            'yayımlanan liste yükün gerçeğiyle uyuşmuyor: %r' % st['metrics'])
        # Eski sözleşme alanları KORUNDU (genişletme, değiştirme değil)
        for anahtar in ('metric', 'range', 'cells', 'stations', 'decimated'):
            assert anahtar in st, 'sözleşme alanı kayboldu: %s' % anahtar
        assert st['cells'] == {'axial': 60, 'radial': 12}

    def test_yukten_silinen_metrik_listeden_duser(self, gercek_alan):
        """Ölçüm gerçekten yükün üstünde: dizi silinirse kimlik düşer."""
        eksik = dict(gercek_alan)
        eksik.pop('pressure_Pa')
        assert _beyan(eksik)['metrics'] == ['mach']

    def test_bos_dizi_de_yok_sayilir(self, gercek_alan):
        """Anahtar var ama dizi boşsa metrik YOKTUR (cfdFieldHasMetric
        uzunluğu da ölçüyor) — 'anahtar var' diye açık düğme bırakılmaz."""
        bos = dict(gercek_alan)
        bos['pressure_Pa'] = []
        assert _beyan(bos)['metrics'] == ['mach']

    def test_yuke_eklenen_metrik_listeye_girer(self, gercek_alan):
        """Liste donmuş bir çift değil: uca sıcaklık gelirse görünür."""
        ni = len(gercek_alan['z_m'])
        nj = len(gercek_alan['r_m'][0])
        ile = dict(gercek_alan)
        ile['temperature_K'] = [[1800.0 + i + 0.5 * j for j in range(nj)]
                                for i in range(ni)]
        assert _beyan(ile)['metrics'] == ['mach', 'pressure', 'temperature']

    def test_alan_yokken_sozluk_de_yok(self):
        """Katman yoksa null döner — boş liste ile 'alan var ama metrik
        yok' hâli karışmaz."""
        out = _emit(_sahne_prelude(),
                    '(function () { var s = new MotorScene(); '
                    'return s.getCfdField(); })()')
        assert out is None

    def test_liste_metrik_kapisiyla_ayni_suzgecten(self, gercek_alan):
        """Yayımlanan liste ile _cfdApplyMetric'in kapısı AYNI ölçümdür:
        tablodaki her kimlik için beyan == cfdFieldHasMetric."""
        out = _emit(_sahne_prelude(),
                    '(function () { var f = %s; return { beyan: '
                    'beyan(f).metrics, dogrudan: CFD_METRICS.filter('
                    'function (m) { return cfdFieldHasMetric(f, m.id); })'
                    '.map(function (m) { return m.id; }) }; })()'
                    % json.dumps(gercek_alan))
        assert out['beyan'] == out['dogrudan'], out

    def test_suzgecin_kopyasi_yazilmamis(self):
        """getCfdField kendi süzgecini KURMAZ; cfdFieldHasMetric'i çağırır.
        (Kopya süzgeç yazılsaydı kapı ile beyan ayrı ayrı sürüklenirdi.)"""
        govde = _extract_method('getCfdField')
        assert 'cfdFieldHasMetric(' in govde, (
            'metrik listesi artık tek kaynaktan ölçülmüyor')
        for kopya in ('payloadKey', 'Array.isArray'):
            assert kopya not in govde, (
                'getCfdField içinde süzgeç kopyası var: %s' % kopya)
        # Kapının kendisi de aynı fonksiyonu kullanmaya devam ediyor
        assert 'cfdFieldHasMetric(' in _extract_method('_cfdApplyMetric')

    def test_cfdResult_genisletilmedi(self):
        """Kapsam disiplini: yalnız getCfdField genişledi. Koşum dönüşü
        (_cfdResult) metrik listesi taşımaz — sözleşmeye gereksiz alan
        eklenmedi."""
        assert 'metrics' not in _extract_method('_cfdResult')

    def test_dis_api_listeyi_tasiyor(self):
        """window.MotorViz3D.getCfdField köprüsü sahnenin metodunu AYNEN
        geçirir (ara katmanda alan kırpılmıyor)."""
        src = _source()
        blok = src[src.index('window.MotorViz3D = {'):]
        assert re.search(r'getCfdField:\s*function\s*\(\)\s*\{\s*return\s+'
                         r'viz \? viz\.getCfdField\(\) : null;', blok), (
            'dış API getCfdField dönüşünü aynen geçirmiyor')


# ---------------------------------------------------------------------------
# b) GÜVERTE — ön-gri kararı SAHNENİN listesinden okunur
# ---------------------------------------------------------------------------

class TestGuverteOnGri:

    def test_yukte_olmayan_metrik_tiklanmadan_gri(self, tmp_path):
        out = kos_guverte(tmp_path, loadedMetric='mach',
                          payloadMetrics=YUK_KURUCU_METRIKLERI)
        b = out['before']
        assert b['buttons']['temperature']['disabled'] is True, (
            'yükte olmayan metriğin düğmesi açık — kullanıcı tıklayıp '
            'reddi yemeden öğrenemiyor')
        assert b['buttons']['mach']['disabled'] is False
        assert b['buttons']['pressure']['disabled'] is False
        assert 'not present in the loaded field' in \
            b['buttons']['temperature']['title'], (
                'gri düğmenin nedeni künyede yazmıyor: %r'
                % b['buttons']['temperature']['title'])
        # ÖN-gri olduğunun kanıtı: sahneye tek bir çağrı bile yapılmadı
        assert not b['calls'], (
            'karar tıklama ölçümünden geliyor: %r' % b['calls'])

    @pytest.mark.parametrize('yuktekiler,gri', [
        (['mach'], ['pressure', 'temperature']),
        (['mach', 'pressure'], ['temperature']),
        (['mach', 'pressure', 'temperature'], []),
    ])
    def test_gri_kumesi_listenin_tumleyeni(self, tmp_path, yuktekiler, gri):
        """Karar listeden okunuyor: gri düğmeler tam olarak listede
        OLMAYANLAR (ne fazla ne eksik)."""
        out = kos_guverte(tmp_path, loadedMetric='mach',
                          payloadMetrics=yuktekiler)
        b = out['before']['buttons']
        olculen = sorted(k for k, v in b.items() if v['disabled'])
        assert olculen == sorted(gri), (
            'gri küme listeyle uyuşmuyor: %r (yükte: %r)'
            % (olculen, yuktekiler))

    def test_liste_degisince_grup_kendiliginden_tazelenir(self, tmp_path):
        """Merkez yeni bir alan bindirince güverte kendiliğinden düzelmeli:
        durum imzası metrik listesini içermezse bu test kırmızıdır."""
        out = kos_guverte(
            tmp_path, loadedMetric='mach',
            payloadMetrics=['mach', 'pressure', 'temperature'],
            tick={'payloadMetrics': ['mach']})
        assert not any(d['disabled'] for d in out['before']['buttons'].values())
        t = out['tick']['buttons']
        assert t['pressure']['disabled'] is True and \
            t['temperature']['disabled'] is True, (
                'liste daralınca düğmeler gri olmadı: %r' % t)
        assert t['mach']['disabled'] is False
        assert not out['tick']['calls'], 'tazeleme sahneyi sürmüş'

    def test_liste_genisleyince_gri_kalkar(self, tmp_path):
        """Ters yön: yeni yükte metrik VARSA eski gri kalkar (bayat karar
        yapışıp kalmaz)."""
        out = kos_guverte(tmp_path, loadedMetric='mach',
                          payloadMetrics=['mach'],
                          tick={'payloadMetrics': ['mach', 'pressure',
                                                   'temperature']})
        assert out['before']['buttons']['temperature']['disabled'] is True
        t = out['tick']['buttons']
        assert not any(d['disabled'] for d in t.values()), (
            'yeni yükte var olan metrik gri kalmış: %r' % t)
        assert 'not present' not in t['temperature']['title']

    def test_tiklama_olcumu_kaldirilmadi(self, tmp_path):
        """Birleşim: liste metriği YÜKTE gösterse bile koşum reddi
        (missing_metric) düğmeyi kapatır — ön-gri onun yerine geçmez."""
        out = kos_guverte(tmp_path, loadedMetric='mach',
                          payloadMetrics=['mach', 'pressure', 'temperature'],
                          missing=['temperature'],
                          click=['_cfd_m_temperature'])
        assert out['before']['buttons']['temperature']['disabled'] is False
        a = out['after']['buttons']['temperature']
        assert a['disabled'] is True, 'koşum reddi düğmeyi kapatmadı'
        assert 'not present in the loaded field' in a['title']

    def test_alan_yokken_hepsi_gri_kalir(self, tmp_path):
        """Liste yokken (alan yüklü değil) beyan da yoktur: grup tümüyle
        gri — uydurma varsayılan liste ile açık düğme basılmaz."""
        out = kos_guverte(tmp_path, payloadMetrics=['mach'])
        assert all(d['disabled'] for d in out['before']['buttons'].values())
        assert out['before']['range'] == '—'


# ---------------------------------------------------------------------------
# c) TEK KAYNAK — güvertede süzgeç kopyası yok
# ---------------------------------------------------------------------------

class TestTekKaynak:

    def test_guvertede_suzgec_kopyasi_yok(self):
        temiz = strip_js_comments(_oku(DECK_JS))
        for kopya in ('cfdFieldHasMetric', 'payloadKey', 'pressure_Pa',
                      'temperature_K'):
            assert kopya not in temiz, (
                'güverte yük anahtarlarına KENDİ bakıyor (%s) — ölçüm '
                'sahnede olmalı' % kopya)

    def test_guverte_listeyi_beyandan_okuyor(self):
        temiz = strip_js_comments(_oku(DECK_JS))
        assert 'Array.isArray(st.metrics)' in temiz, (
            'güverte sahnenin metrics listesini okumuyor')
        # Liste imzaya girmeli: değişimi yakalayan tek yol budur
        imza = temiz[temiz.index('function cfdStateSig'):]
        imza = imza[:imza.index('function cfdDefaultStatus')]
        assert 'cfdPayloadMetrics(st)' in imza, (
            'durum imzası metrik listesini içermiyor — liste değişince '
            'grup tazelenmez')
