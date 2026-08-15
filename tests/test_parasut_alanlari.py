"""Hibrit sayfasının paraşüt (kurtarma) üçlüsü: form -> istek -> çözücü.

2.6.27 yirmi ikinci partinin artçı kalemi — "kanal var kapı yok" sınıfı.
``/calculate`` üç kurtarma anahtarını ZATEN okuyordu (``app.py`` içinde
``launch_params['parachute_area' | 'parachute_cd' |
'parachute_deploy_delay']``) ve katı sayfasında bu üç alan Faz 6'da
açılmıştı; HİBRİT sayfasında alan yoktu. Ölçülen sonuç: hibritte iniş hızı
araçtan bağımsız, çözücünün belgelenmiş varsayımından türüyordu ve üç
büyüklüğün üçü de ``assumed=true`` damgası taşıyordu — damga dürüsttü ama
kullanıcının onu DÜZELTMESİNİN yolu yoktu.

Bu dosya iki dikişi birden kilitler:

1. ŞABLON DİKİŞİ (statik + node koşumu): üç alan sayfada var, toplayıcıda
   ``optNum`` ile okunuyor, alanlara SAYI DAYATILMIYOR (``value``
   özniteliği yok) ve BOŞ alanın anahtarı isteğe HİÇ konmuyor.
2. ÇÖZÜCÜ DİKİŞİ (test_client): dolu değer ``trajectory.recovery``e aynen
   ulaşıyor, boş bırakılınca varsayım beyanı sürüyor.

İkincisi olmadan birincisi "gönderiliyor ama işe yaramıyor"u göremez;
birincisi olmadan ikincisi "arka uç bağlı ama kullanıcı giremiyor"u
göremez (v2.6.25 hibrit termal alanlarının tam olarak düştüğü tuzak).

ÖLÇÜM (bu dosya yazılırken, ``HYBRID_BASE`` üstünde):

======================  ===============  ===============  ==============
istek                   alan / Cd / gec  assumed          iniş hızı
======================  ===============  ===============  ==============
anahtar yok             2,0 / 1,4 / 2,0  üçü de True      22,62 m/s
9,0 / 0,9 / 5,0         9,0 / 0,9 / 5,0  üçü de False     13,29 m/s
boş dize ('')           2,0 / 1,4 / 2,0  üçü de True      22,62 m/s
======================  ===============  ===============  ==============

Yani üçlü %41 iniş hızı farkı yaratıyor; boş dize tabanla BİT-AYNI yanıt
veriyor (``app.py`` boş anahtarı düşürüyor, beyan bozulmuyor).
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.support import inventory, shake

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ADVANCED_HTML = REPO_ROOT / 'hrma' / 'templates' / 'advanced.html'
NODE = shutil.which('node')

#: Şablon alan kimliği -> istek anahtarı (bu üçlüde ikisi aynı).
ALANLAR = ('parachute_area', 'parachute_cd', 'parachute_deploy_delay')

#: Çözücünün belgelenmiş varsayımları (trajectory_analysis.py sabitleri).
VARSAYIM = {'parachute_area_m2': 2.0, 'parachute_cd': 1.4,
            'parachute_deploy_delay_s': 2.0}

#: Ölçümde kullanılan dolu istek (varsayımdan BELİRGİN farklı üç değer).
DOLU = {'parachute_area': 9.0, 'parachute_cd': 0.9,
        'parachute_deploy_delay': 5.0}


@pytest.fixture(scope='module')
def markup():
    return ADVANCED_HTML.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def taban_yanit(client):
    from tests.test_field_wiring_layer_b import HYBRID_BASE
    resp = client.post('/calculate', json=dict(HYBRID_BASE),
                       headers=shake.HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()


@pytest.fixture(scope='module')
def dolu_yanit(client):
    from tests.test_field_wiring_layer_b import HYBRID_BASE
    resp = client.post('/calculate', json=dict(HYBRID_BASE, **DOLU),
                       headers=shake.HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()


# ---------------------------------------------------------------------------
# 1. Şablon dikişi
# ---------------------------------------------------------------------------

def test_uc_alan_hibrit_sayfasinda_var(markup):
    """Alanlar sayfada olmadan kullanıcı varsayımı düzeltemez."""
    eksik = [a for a in ALANLAR if ('id="%s"' % a) not in markup]
    assert not eksik, (
        'advanced.html icinde su kurtarma alanlari yok: %s' % eksik)


def test_uc_alan_toplayiciya_bagli():
    """Katman A'nın gördüğü toplayıcıda (getFormData) okunuyorlar.

    Yerel takma adla (``chuteNum`` gibi) yazılırsa envanter deseni alanları
    'hicbir yerde okunmuyor' sayar; 2.6.27 yirminci partide sıvı sayfasında
    tam olarak bu yaşandı. Ad SÖZLEŞMEDİR.
    """
    envanter = inventory.build('hybrid')
    for alan in ALANLAR:
        assert alan in envanter.template_fields, alan
        assert alan in envanter.collected_fields, (
            '%s getFormData icinde okunmuyor (takma ad tuzagi?)' % alan)


def test_toplayici_blogu_return_dan_ONCE(markup):
    """Blok ``return data``dan SONRAYA kayarsa üçlü sessizce ölür.

    Bu dosyanın öbür bekçilerinin hiçbiri bunu göremez: envanter deseni
    metin arar (``optNum('parachute_area')`` ölü kodda da eşleşir), node
    koşumu ise bloğu şablondan KESİP ayrı çalıştırır — yani bloğun gövde
    içindeki YERİNİ ölçmez. Erişilemez toplayıcı, tam olarak bu partinin
    kapattığı 'kanal var kapı yok' kusurunun sessiz biçimidir: alan
    sayfada durur, okuyucu kodda durur, istek yine boş gider.
    """
    govde = _getformdata_govdesi(markup)
    blok = govde.index("const optNum = function (id) {")
    donusler = [m.start() for m in re.finditer(r'\breturn\s+data\b', govde)]
    assert donusler, 'getFormData icinde "return data" yok (kalip degismis)'
    assert all(blok < d for d in donusler), (
        'Parasut toplayici blogu getFormData icindeki return data\'dan '
        'SONRA: erisilemez kod, ucu istege hic girmez.')


def _getformdata_govdesi(kaynak):
    """``getFormData`` gövdesini süslü parantez sayarak ayıklar."""
    bas = kaynak.index('function getFormData')
    ac = kaynak.index('{', bas)
    derinlik = 0
    for konum in range(ac, len(kaynak)):
        if kaynak[konum] == '{':
            derinlik += 1
        elif kaynak[konum] == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[ac:konum]
    raise AssertionError('getFormData govdesi kapanmiyor')


def test_alanlara_sayi_dayatilmiyor(markup):
    """Üç alanın da ``value`` özniteliği YOK: boş açılırlar.

    Varsayılan sayı basmak, kullanıcının girmediği bir paraşütü onun
    girdisiymiş gibi göstermek olurdu — ``assumed`` beyanı da sessizce
    düşerdi. Boşluk burada bilinçli bir sözleşmedir.
    """
    for alan in ALANLAR:
        etiket = re.search(r'<input[^>]*id="%s"[^>]*>' % alan, markup)
        assert etiket, alan
        assert 'value=' not in etiket.group(0), (
            '%s alanina varsayilan sayi dayatilmis: %s'
            % (alan, etiket.group(0)))
        assert 'min="0"' in etiket.group(0), alan


def _toplayici_blogu(kaynak):
    """Paraşüt toplayıcı bloğunu şablondan ayıklar (node ile koşmak için)."""
    bas = kaynak.index('const optNum = function (id) {')
    orta = kaynak.index('Object.keys(chute).forEach(function (k) {', bas)
    son = kaynak.index('});', orta) + len('});')
    return kaynak[bas:son]


_HARNESS = """'use strict';
var _alanlar = %s;
var document = {
    getElementById: function (id) {
        return Object.prototype.hasOwnProperty.call(_alanlar, id)
            ? { value: _alanlar[id] } : null;
    }
};
var data = {};
%s
console.log(JSON.stringify(data));
"""


def _kosur(tmp_path, alanlar, markup):
    betik = tmp_path / 'chute.js'
    betik.write_text(
        _HARNESS % (json.dumps(alanlar), _toplayici_blogu(markup)),
        encoding='utf-8')
    sonuc = subprocess.run([NODE, str(betik)], capture_output=True, text=True)
    assert sonuc.returncode == 0, sonuc.stderr
    return json.loads(sonuc.stdout)


@pytest.mark.skipif(NODE is None, reason='node kurulu degil')
def test_bos_alan_anahtari_istege_koymaz(tmp_path, markup):
    """BOŞ alan -> anahtar isteğe HİÇ girmez (varsayım beyanının ön koşulu).

    ``getv``/``numById`` gibi bir okuyucu boş alanda ya yedek sayı ya null
    döndürüp anahtarı yine gönderirdi; çözücü 'verilmedi' ile 'değer geldi'
    ayrımını anahtarın VARLIĞINDAN yapıyor (trajectory_analysis.py:518).
    Anahtar gönderilirse kullanıcının hiç vermediği bir paraşüt beyan
    edilmiş olur ve ``assumed`` damgası haksız yere düşer.
    """
    data = _kosur(tmp_path, {a: '' for a in ALANLAR}, markup)
    assert not [a for a in ALANLAR if a in data], data


@pytest.mark.skipif(NODE is None, reason='node kurulu degil')
def test_dolu_alan_degeri_akar(tmp_path, markup):
    data = _kosur(tmp_path, {'parachute_area': '9', 'parachute_cd': '0.9',
                             'parachute_deploy_delay': '5'}, markup)
    assert data == {'parachute_area': 9.0, 'parachute_cd': 0.9,
                    'parachute_deploy_delay': 5.0}, data


@pytest.mark.skipif(NODE is None, reason='node kurulu degil')
def test_gecersiz_deger_gonderilmez(tmp_path, markup):
    """0 / negatif / metin -> anahtar gönderilmez (uydurma değer yasak).

    Sıfır alanlı paraşüt fiziksel değil; çözücü de pozitif olmayanı
    reddedip varsayıma dönerdi (set_recovery_parameters:188-209) ama o
    durumda 'kullanıcı verdi' bayrağı yanlış yönde oynardı.
    """
    data = _kosur(tmp_path, {'parachute_area': '0', 'parachute_cd': '-1',
                             'parachute_deploy_delay': 'abc'}, markup)
    assert data == {}, data


# ---------------------------------------------------------------------------
# 2. Çözücü dikişi
# ---------------------------------------------------------------------------

def test_bos_birakilinca_varsayim_beyani_surer(taban_yanit):
    """Anahtar gönderilmezse çözücü varsayımı sürdürür ve BEYAN eder."""
    rec = taban_yanit['trajectory']['recovery']
    assert rec['deployed'] is True
    for anahtar, deger in VARSAYIM.items():
        assert rec[anahtar] == pytest.approx(deger), (anahtar, rec[anahtar])
    assert rec['assumed'] == {'area': True, 'cd': True, 'deploy_delay': True}
    kodlar = {w.get('code') for w in
              (taban_yanit['trajectory'].get('warnings') or [])}
    assert 'warn.trajectory.parachute_area_assumed' in kodlar, kodlar


def test_dolu_deger_kurtarma_blogunda_aynen_durur(dolu_yanit):
    """Kullanıcının üç sayısı ``trajectory.recovery``e AYNEN ulaşır."""
    rec = dolu_yanit['trajectory']['recovery']
    assert rec['parachute_area_m2'] == pytest.approx(9.0)
    assert rec['parachute_cd'] == pytest.approx(0.9)
    assert rec['parachute_deploy_delay_s'] == pytest.approx(5.0)


def test_dolu_deger_varsayim_damgasini_kaldirir(dolu_yanit):
    """Üç bileşen de kullanıcıdan gelince ``assumed`` üçü için de düşer."""
    rec = dolu_yanit['trajectory']['recovery']
    assert rec['assumed'] == {'area': False, 'cd': False,
                              'deploy_delay': False}
    kodlar = {w.get('code') for w in
              (dolu_yanit['trajectory'].get('warnings') or [])}
    assert 'warn.trajectory.parachute_area_assumed' not in kodlar, kodlar


def test_inis_hizi_gercekten_degisir(taban_yanit, dolu_yanit):
    """Üçlü SONUCU değiştirmeli — yoksa alan 'bağlandı' ama ölüdür.

    Ölçüldü: 22,62 m/s -> 13,29 m/s (%41,2). ``landing_velocity`` bir
    GÜVENLİK metriği olarak okunuyor; kullanıcının onu düzeltebilmesi bu
    partinin bütün gerekçesi.
    """
    taban = taban_yanit['trajectory']['recovery']['landing_velocity_m_s']
    dolu = dolu_yanit['trajectory']['recovery']['landing_velocity_m_s']
    assert taban > 0 and dolu > 0
    assert abs(dolu - taban) / taban > 0.1, (taban, dolu)


def test_bos_dize_tabanla_bit_ayni(client, taban_yanit):
    """``parachute_area: ''`` gönderen istemci tabanla AYNI yanıtı alır.

    ``app.py`` boş/None anahtarı ``launch_params``tan düşürüyor
    (:1784-1785); bu bekçi o filtrenin kaldırılmasını yakalar — kaldırılsa
    boş alan 'verildi' sayılır ve varsayım beyanı sessizce yalan söylerdi.
    """
    from tests.test_field_wiring_layer_b import HYBRID_BASE
    resp = client.post('/calculate',
                       json=dict(HYBRID_BASE, parachute_area='',
                                 parachute_cd='', parachute_deploy_delay=''),
                       headers=shake.HEADERS)
    assert resp.status_code == 200
    assert resp.get_json()['trajectory']['recovery'] == \
        taban_yanit['trajectory']['recovery']
