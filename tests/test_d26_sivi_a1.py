"""ÖH D26 · sivi · a1 — P16B3-02 (KALAN): SESSİZ SOĞUTMA SEÇİMİ BİTTİ.

Kalem başlığı: "soğutma menüsündeki 5 seçenekten 4'ü modellenmiyor —
sessizce SOĞUTMASIZ sonuç, kullanıcının etiketi altında".

D25 (app-api a2) başlığın İKİ ayağını ayırdı: hibrit ``/calculate``
ailesindeki tanınmayan-kelime ayağı ONARILDI (beyaz-liste kapısı), sıvı
ayağındaki "sessizce soğutmasız" iddiası ise ÇÜRÜDÜ (sıvı uç çözülmemiş
cidarı ``wall_temperature_status='not_solved'`` künyesiyle geri çekiyor).
Geriye ölçülüp DOKUNULMAMIŞ tek şey kaldı: **varsayılanın kendisi
sessizdi**.

ÖLÇÜLDÜ (``docs/scofield/raw/OH/D26/sivi/a1/once.json``, taban
``7751531``): ``/calculate_liquid``a ``cooling_type`` GÖNDERMEYEN gövde ile
``cooling_type: 'regenerative'`` gönderen gövde bit-aynıydı — 4.347
yaprağın **0**'ı farklı, sha256 birebir eşit. Yanıt ise üç yaprakta o
değeri kullanıcının seçimiymiş gibi basıyordu. Seçim sonuçsuz değil:
``film_cooling`` ile aynı gövde **891 yaprak** ayrışıyor. ``injector_type``
(bölüm B) birebir aynı biçim, aynı uç, aynı satırların altı.

ONARIM ÖK-19'un İKİNCİ şıkkı: kapı zaten vardı, kapının ALTINDAKİ sessiz
düşüş ``defaults_applied`` künyesiyle adıyla yayımlanıyor. Sayı ve fizik
DEĞİŞMEDİ (bekçi bunu ayrıca ölçer: künye çıkarılınca iki gövde bit-aynı).
"""
import ast
import hashlib
import json
import os
import re

import pytest

from hrma.app import (
    HIBRIT_SOGUTMA_VARSAYILANI,
    LIQUID_COOLING_TYPE_DEFAULT,
    LIQUID_INJECTOR_TYPE_DEFAULT,
    app,
)

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PY = os.path.join(KOK, 'hrma', 'app.py')
LIQUID_HTML = os.path.join(KOK, 'hrma', 'templates', 'liquid.html')
ADVANCED_HTML = os.path.join(KOK, 'hrma', 'templates', 'advanced.html')

#: Hibrit ``/calculate`` ailesinin kapıyı GEÇEN asgari gövdesi.
#: ``cooling_channels`` BİLEREK yoktur — ölçülen kusur tam olarak budur
#: (``once_hibrit.json``).
HIBRIT = {'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
          'chamber_pressure': 20, 'of_ratio': 6.0, 'fuel_type': 'htpb',
          'oxidizer_type': 'n2o', 'expansion_ratio': 8,
          'atmospheric_pressure': 1.0}

#: Kabulün düştüğü üç uç. ``/api/transient-analysis`` yanıtında soğutma
#: seçimi HİÇ yaprak oynatmıyor (ölçüldü: 0/3233) ama kabul YİNE DE
#: yapılıyor, o yüzden künye orada da doğar.
HIBRIT_UCLAR = ('/calculate', '/api/quick-geometry',
                '/api/transient-analysis')

#: Kapının GEÇTİĞİ asgari sıvı gövdesi. Soğutma ve enjektör seçimi BİLEREK
#: yoktur — ölçülen kusur tam olarak budur.
SIVI = {'motor_name': 'D26-SIVI-A1', 'thrust': 10000.0, 'burn_time': 30.0,
        'chamber_pressure': 30.0, 'mixture_ratio': 2.2,
        'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'expansion_ratio': 12.0}


@pytest.fixture(scope='module')
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _menunun_ilk_secenegi(select_id):
    """``liquid.html``in KENDİ menüsünün ilk ``<option value=...>``i.

    Beklenen değer BİLEREK ``app.py``den okunmaz: D25 app-api a2'de aynı
    hatanın mutasyonu ilk turda YEŞİL çıkmıştı, çünkü bekçi beklenen
    varsayılanı sabitin kendisinden alıyordu (totoloji). Ürünün kaynağı
    kullanıcının gördüğü menüdür.
    """
    metin = open(LIQUID_HTML, encoding='utf-8').read()
    m = re.search(r'<select\s+id="%s"[^>]*>(.*?)</select>' % select_id,
                  metin, re.S)
    assert m, f'liquid.html içinde <select id="{select_id}"> bulunamadı'
    secenekler = re.findall(r'<option\s+value="([^"]*)"', m.group(1))
    assert secenekler, f'{select_id} menüsünde <option> yok'
    return secenekler[0]


def _kunye(govde, alan):
    for k in (govde or {}).get('defaults_applied') or []:
        if isinstance(k, dict) and k.get('field') == alan:
            return k
    return None


def _sha(govde):
    return hashlib.sha256(
        json.dumps(govde, sort_keys=True, ensure_ascii=False,
                   default=repr).encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# 1) Kusurun kendisi: gönderilmeyen seçim artık ADIYLA beyan ediliyor
# ---------------------------------------------------------------------------
class TestSessizVarsayilanBitti:

    def test_cooling_type_gonderilmeyince_kunye_yayimlanir(self, client):
        r = client.post('/calculate_liquid', json=dict(SIVI))
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        govde = r.get_json()
        k = _kunye(govde, 'cooling_type')
        assert k is not None, (
            'cooling_type gönderilmedi ama yanıt bunu beyan etmiyor — '
            "sunucunun varsayımı kullanıcının seçimiymiş gibi yayımlanıyor "
            '(ÖK-19: varsayılan kalacaksa defaults_applied ZORUNLU).')
        assert k['reason'] == 'not_supplied', k
        assert k['value'] == LIQUID_COOLING_TYPE_DEFAULT, k
        assert k['applied_by'], k
        assert 'assumption, not a result' in k['message'], k
        # Künye YALAN SÖYLEMEZ: beyan edilen değer, gövdenin yayımladığı
        # değerle aynı olmalı.
        assert govde['cooling_type'] == LIQUID_COOLING_TYPE_DEFAULT

    def test_injector_type_gonderilmeyince_kunye_yayimlanir(self, client):
        r = client.post('/calculate_liquid', json=dict(SIVI))
        assert r.status_code == 200
        k = _kunye(r.get_json(), 'injector_type')
        assert k is not None, 'injector_type düşüşü sessiz kaldı'
        assert k['reason'] == 'not_supplied', k
        assert k['value'] == LIQUID_INJECTOR_TYPE_DEFAULT, k

    @pytest.mark.parametrize('deger', [None, '', '   '])
    def test_bos_deger_de_GONDERILMEDI_sayilir(self, client, deger):
        """Uç geneli ilke: None / boş dize "gönderilmedi"dir.

        Davranış TABANLA AYNI (değer yine varsayılan olur, gövde reddedilmez);
        değişen tek şey, artık beyan edilmesidir.
        """
        r = client.post('/calculate_liquid',
                        json=dict(SIVI, cooling_type=deger))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert _kunye(r.get_json(), 'cooling_type') is not None, deger

    def test_acik_secim_kendi_kunyesini_URETMEZ(self, client):
        """Kullanıcı seçtiyse O SEÇİMİN künyesi YOK — iddia ALANA bağlı.

        ÖH D37 A1a uc-kapi (OH-D32-02 kanonik künye; ana model kararı,
        rapor ``docs/scofield/raw/OH/A1a/uc-kapi/a1/rapor.md`` §1.5) —
        BEKÇİ ÇEVRİLDİ, gerekçesi: eski ölçü ``'defaults_applied' not in
        govde`` idi. O önerme ``SIVI`` gövdesinin DIŞINDA kalan alanların
        (``chamber_roughness``, ``coolant_flow_percent``,
        ``coolant_inlet_temp``, ``safety_factor``, ``turbopump_efficiency``)
        SESSİZLİĞİNE dayanıyordu; kanonik künye tam o sessizliği kaldırıyor —
        gövdede olmayan o alanlar artık ADIYLA sayılıyor. Korunan niyet
        (zayıflamadan): açık seçim KENDİ künyesini üretmez, künye gövdede
        bulunan HİÇBİR alanı anmaz ve seçimin künyeye tek etkisi kendi iki
        künyesinin düşmesidir (küme farkı tam olarak iki alan). Fizik
        dokunulmazlığı ``TestAyirtEdilebilirlik``te ayrıca ölçülür.
        """
        istek = dict(SIVI, cooling_type='regenerative',
                     injector_type='impinging')
        r = client.post('/calculate_liquid', json=istek)
        assert r.status_code == 200
        govde = r.get_json()
        adlar = {k['field'] for k in govde.get('defaults_applied') or []}
        assert not adlar & {'cooling_type', 'injector_type'}, (
            'İki seçim de gönderildi ama uç yine de o seçimleri varsayılan '
            f"diye bildiriyor: {govde.get('defaults_applied')}")
        assert not adlar & set(istek), (
            'künye istekte GELEN alan(lar)ı varsayılan diye anıyor: '
            f'{sorted(adlar & set(istek))}')
        secimsiz = client.post('/calculate_liquid', json=dict(SIVI))
        assert secimsiz.status_code == 200
        secimsiz_adlar = {k['field'] for k in
                          secimsiz.get_json()['defaults_applied']}
        assert secimsiz_adlar ^ adlar == {'cooling_type', 'injector_type'}, (
            'açık seçim künyede kendi iki alanından BAŞKA bir şeyi de '
            f'değiştirdi: seçimsiz {sorted(secimsiz_adlar)} ⟷ seçimli '
            f'{sorted(adlar)}')

    def test_TEK_alan_dusunce_YALNIZ_o_alan_beyan_edilir(self, client):
        """Düşürülen TEK seçim künyede; verilen seçim künyede DEĞİL.

        ÖH D37 A1a uc-kapi (OH-D32-02 kanonik künye; ana model kararı) —
        BEKÇİ ÇEVRİLDİ, gerekçesi: eski ölçü künye kümesinin TAMAMEN
        ``{'injector_type'}`` olmasıydı; bu da gövde dışındaki kanonik
        alanların sessizliğine dayanıyordu. Korunan niyet: tek alan
        düşünce YALNIZ o alan yeni beyan olur — aynı gövde düşen alan
        eklenerek TAM gönderildiğinde künye farkı tam olarak
        ``{'injector_type'}`` kalır, kalan künyeler tam gövdede zaten
        OLMAYAN kanonik alanlardır (``endpoint_default``).
        """
        tek = dict(SIVI, cooling_type='film_cooling')
        r = client.post('/calculate_liquid', json=tek)
        assert r.status_code == 200
        kunye = {k['field']: k for k in r.get_json()['defaults_applied']}
        assert 'injector_type' in kunye, 'düşürülen alan künyesiz kaldı'
        assert 'cooling_type' not in kunye, (
            f'kullanıcının VERDİĞİ alan varsayılan diye beyan edildi: '
            f'{sorted(kunye)}')
        tam = dict(tek, injector_type=kunye['injector_type']['value'])
        r_tam = client.post('/calculate_liquid', json=tam)
        assert r_tam.status_code == 200
        tam_kunye = {k['field']: k for k in
                     r_tam.get_json().get('defaults_applied') or []}
        assert set(kunye) ^ set(tam_kunye) == {'injector_type'}, (
            'tek alan düştü ama künye başka alan(lar)da da değişti: '
            f'tek {sorted(kunye)} ⟷ tam {sorted(tam_kunye)}')
        assert not set(tam_kunye) & set(tam), (
            'tam gövdede GELEN alan künyede: '
            f'{sorted(set(tam_kunye) & set(tam))}')
        for ad, k in tam_kunye.items():
            assert k['reason'] == 'endpoint_default', (ad, k)


# ---------------------------------------------------------------------------
# 2) Ayırt edilebilirlik + fizik dokunulmazlığı (kalemin özü)
# ---------------------------------------------------------------------------
class TestAyirtEdilebilirlik:

    def test_gonderilen_ile_gonderilmeyen_govde_ARTIK_AYIRT_EDILEBILIR(
            self, client):
        """Kusurun tam ölçüsü: tabanda bu iki gövde bit-aynıydı."""
        yok = client.post('/calculate_liquid', json=dict(SIVI)).get_json()
        acik = client.post('/calculate_liquid',
                           json=dict(SIVI, cooling_type='regenerative',
                                     injector_type='impinging')).get_json()
        assert _sha(yok) != _sha(acik), (
            'Soğutma/enjektör seçimini GÖNDERMEYEN gövde ile açıkça SEÇEN '
            'gövde hâlâ bit-aynı: kullanıcı, sonucun kendi seçimiyle mi '
            'yoksa sunucunun varsayımıyla mı üretildiğini ayırt edemiyor.')

    def test_KUNYE_DISINDA_hicbir_sayi_degismedi(self, client):
        """Beyan bir hüküm değişikliği DEĞİLDİR: fizik bit-aynı kalmalı.

        ``defaults_applied`` çıkarıldığında iki gövde birebir eşit olmalı —
        aksi hâlde onarım sessizce bir sayıyı da kaydırmış olurdu.
        """
        yok = client.post('/calculate_liquid', json=dict(SIVI)).get_json()
        acik = client.post('/calculate_liquid',
                           json=dict(SIVI, cooling_type='regenerative',
                                     injector_type='impinging')).get_json()
        yok.pop('defaults_applied', None)
        acik.pop('defaults_applied', None)
        assert _sha(yok) == _sha(acik), (
            'Künye dışında da fark var: onarım yalnız beyan eklemedi, '
            'ürünün sayısını da değiştirdi.')

    def test_secim_SONUCSUZ_degil_891_yaprak(self, client):
        """Varsayılanın neden önemli olduğunun ölçümü (once.json bölüm A)."""
        regen = client.post('/calculate_liquid',
                            json=dict(SIVI,
                                      cooling_type='regenerative')).get_json()
        film = client.post('/calculate_liquid',
                           json=dict(SIVI,
                                     cooling_type='film_cooling')).get_json()

        def duz(x, on='', b=None):
            b = {} if b is None else b
            if isinstance(x, dict):
                for k, v in x.items():
                    duz(v, f'{on}.{k}' if on else str(k), b)
            elif isinstance(x, list):
                for i, v in enumerate(x):
                    duz(v, f'{on}[{i}]', b)
            else:
                b[on] = repr(x)
            return b
        a, c = duz(regen), duz(film)
        farkli = sum(1 for k in set(a) | set(c) if a.get(k) != c.get(k))
        assert farkli > 500, (
            f'soğutma seçimi yalnız {farkli} yaprak değiştiriyor; kalemin '
            'dayandığı "seçim sonucu belirler" önermesi ölçümle zayıfladı')


# ---------------------------------------------------------------------------
# 3) Tek kaynak (doktrin 4) — totolojisiz
# ---------------------------------------------------------------------------
class TestTekKaynak:

    def test_varsayilan_URUNUN_KENDI_menusunun_ilk_secenegidir(self):
        assert LIQUID_COOLING_TYPE_DEFAULT == _menunun_ilk_secenegi(
            'cooling_type'), (
            'Uç varsayılanı ile liquid.html soğutma menüsünün ilk seçeneği '
            'ayrıştı: kullanıcı formu açtığında gördüğü seçenek ile alanı '
            'göndermediğinde uygulanan seçenek farklı olur.')
        assert LIQUID_INJECTOR_TYPE_DEFAULT == _menunun_ilk_secenegi(
            'injector_type')

    def test_uc_govdesinde_ELLE_YAZILI_varsayilan_kalmadi(self):
        """``calculate_liquid`` gövdesi artık dizeyi kendisi yazmıyor.

        AST ile ölçülür — yorum ve belge dizesi sayılmaz.
        """
        agac = ast.parse(open(APP_PY, encoding='utf-8').read())
        hedef = None
        for d in ast.walk(agac):
            if isinstance(d, ast.FunctionDef) and d.name == 'calculate_liquid':
                hedef = d
                break
        assert hedef is not None, 'calculate_liquid bulunamadı'
        govde = list(hedef.body)
        if (govde and isinstance(govde[0], ast.Expr)
                and isinstance(govde[0].value, ast.Constant)):
            govde = govde[1:]
        yazili = []
        for d in govde:
            for n in ast.walk(d):
                if isinstance(n, ast.Constant) and n.value in (
                        LIQUID_COOLING_TYPE_DEFAULT,
                        LIQUID_INJECTOR_TYPE_DEFAULT):
                    yazili.append(n.value)
        assert not yazili, (
            'uç gövdesinde elle yazılı varsayılan kaldı: '
            f'{sorted(set(yazili))} — değer LIQUID_*_DEFAULT tek '
            'kaynağından okunmalı (doktrin 4)')

    def test_sabit_dosyada_TEK_KEZ_taniml(self):
        metin = open(APP_PY, encoding='utf-8').read()
        assert metin.count('LIQUID_COOLING_TYPE_DEFAULT = ') == 1
        assert metin.count('LIQUID_INJECTOR_TYPE_DEFAULT = ') == 1


# ---------------------------------------------------------------------------
# 4) Künye sözleşmesi: TEK biçim, iki GEREKÇE
# ---------------------------------------------------------------------------
class TestKunyeSozlesmesi:

    def test_ogretici_kip_ile_menu_varsayilani_AYRISABILIR(self, client):
        r = client.post('/calculate_liquid',
                        json={'use_tutorial_defaults': True})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        govde = r.get_json()
        assert govde['input_source'] == 'tutorial_defaults'
        beyan = govde['defaults_applied']
        assert beyan, 'öğretici kip beyansız kaldı'
        assert all(isinstance(k, dict) for k in beyan), (
            f'defaults_applied karışık tipli: {beyan}')
        gerekceler = {k['reason'] for k in beyan}
        assert {'tutorial_default', 'not_supplied'} <= gerekceler, (
            'tanıtım girdisi ile menü varsayılanı aynı listede ayırt '
            f'edilemiyor: {gerekceler}')
        for k in beyan:
            assert k.get('field') and k.get('applied_by') and k.get('message')
        adlar = {k['field'] for k in beyan}
        assert {'cooling_type', 'injector_type'} <= adlar, adlar

    def test_RET_govdesi_varsayilan_bildirmez(self, client):
        """Kapı reddederken hiçbir varsayılan uygulanmamıştır."""
        r = client.post('/calculate_liquid', json={})
        assert r.status_code == 422
        assert 'defaults_applied' not in (r.get_json() or {})


# ---------------------------------------------------------------------------
# 5) Gerileme: kapı hâlâ kapalı (ÖK-22 — sağlıklı envanter gevşetilemez)
# ---------------------------------------------------------------------------
class TestKapiAyakta:

    @pytest.mark.parametrize('deger', ['regenerativ', 'banana', 'none', 0,
                                       True, ['regenerative']])
    def test_taninmayan_cooling_type_hala_422(self, client, deger):
        r = client.post('/calculate_liquid',
                        json=dict(SIVI, cooling_type=deger))
        assert r.status_code == 422, (
            f'{deger!r} için 200 dönüldü — D15/P7B2-08 kapısı gevşemiş')
        govde = r.get_json()
        assert govde['error'] == 'unsupported_cooling_type'
        assert govde['invalid_fields'][0]['field'] == 'cooling_type'
        assert 'defaults_applied' not in govde

    def test_taninmayan_injector_type_hala_422(self, client):
        r = client.post('/calculate_liquid',
                        json=dict(SIVI, injector_type='banana'))
        assert r.status_code == 422
        assert r.get_json()['error'] == 'unsupported_injector_type'

    def test_menunun_HER_secenegi_motorda_cozuluyor(self):
        """Şablon ⟷ motor zinciri: menüye ölü seçenek eklenirse kırar."""
        from hrma.engines.liquid_rocket_engine import (
            COOLING_TYPES_RECOGNISED, INJECTOR_TYPES_RECOGNISED)
        metin = open(LIQUID_HTML, encoding='utf-8').read()
        for select_id, tanimli in (('cooling_type', COOLING_TYPES_RECOGNISED),
                                   ('injector_type',
                                    INJECTOR_TYPES_RECOGNISED)):
            m = re.search(r'<select\s+id="%s"[^>]*>(.*?)</select>' % select_id,
                          metin, re.S)
            secenekler = re.findall(r'<option\s+value="([^"]*)"', m.group(1))
            olu = [s for s in secenekler
                   if s.strip().lower() not in tanimli]
            assert not olu, (
                f'{select_id} menüsünde motorun çözemediği seçenek var: {olu}')


# ===========================================================================
# HİBRİT AYAK — P16B3-02 (KALAN): ``cooling_channels`` sessiz ``'none'``
# ===========================================================================
# ÖLÇÜLDÜ (``once_hibrit.json``, taban ``7751531``): alanı HİÇ göndermeyen
# gövde ile açıkça ``cooling_channels='none'`` gönderen gövde BİT-AYNIYDI —
# ``/calculate`` 36.085 yaprakta 0 fark, ``/api/quick-geometry`` 8.000'de 0,
# ``/api/transient-analysis`` 3.233'te 0; sha256 üçünde de eşit. Yanıt bu
# kabulle ``cooling_type='natural'``, ``cooling_efficiency=0,3`` ve
# ``required_cooling_area=468,47 m²`` yayımlıyordu: 1 kN'luk motora 468 m²
# soğutma alanı, yani DOĞAL TAŞINIMIN (soğutmasız) sayıları — kullanıcının
# hiç seçmediği bir tasarım sınıfı, sonucun kendi etiketi altında.
#
# D25 (app-api a2) yalnız TANINMAYAN kelimeyi kapattı. ÖK-19: "kapı tek
# başına yetmez; altındaki varsayılan aynı commit'te beyan edilir ya da
# kalkar". Fail-closed ölçülerek elendi: ``/calculate`` çağıran 110 test
# dosyasının yalnız 4'ü bu alanı gönderiyor, ürünün kendi üç-motor çapa
# gövdesi de göndermiyor.


def _hibrit_menunun_ilk_secenegi():
    """``advanced.html``in KENDİ ``cooling_channels`` menüsünün ilk değeri.

    Sıvı taraftaki kardeşiyle aynı gerekçe: beklenen varsayılan BİLEREK
    ``app.py``den okunmaz (totoloji tuzağı), ürünün kaynağı kullanıcının
    gördüğü menüdür.
    """
    metin = open(ADVANCED_HTML, encoding='utf-8').read()
    m = re.search(r'<select\s+id="cooling_channels"[^>]*>(.*?)</select>',
                  metin, re.S)
    assert m, 'advanced.html içinde <select id="cooling_channels"> yok'
    secenekler = re.findall(r'<option\s+value="([^"]*)"', m.group(1))
    assert secenekler, 'cooling_channels menüsünde <option> yok'
    return secenekler[0]


def _yapraklar(x, on='', bic=None):
    if bic is None:
        bic = {}
    if isinstance(x, dict):
        if not x:
            bic[on] = '{}'
        for k, v in x.items():
            _yapraklar(v, f'{on}.{k}' if on else str(k), bic)
    elif isinstance(x, list):
        if not x:
            bic[on] = '[]'
        for i, v in enumerate(x):
            _yapraklar(v, f'{on}[{i}]', bic)
    else:
        bic[on] = repr(x)
    return bic


class TestHibritSessizNoneBitti:
    """Gönderilmeyen ``cooling_channels`` artık ADIYLA beyan ediliyor."""

    @pytest.mark.parametrize('yol', HIBRIT_UCLAR)
    def test_alan_yoksa_kunye_yayimlanir(self, client, yol):
        g = client.post(yol, json=dict(HIBRIT)).get_json()
        k = _kunye(g, 'cooling_channels')
        assert k is not None, (
            f'{yol}: cooling_channels gönderilmedi ve SOĞUTMASIZ ("none") '
            f'çözüldü, ama yanıt bunu beyan etmiyor (ÖK-19).')
        assert k['reason'] == 'not_supplied'
        assert k['value'] == HIBRIT_SOGUTMA_VARSAYILANI
        # Künye GERÇEĞİ söylemeli: kabulün soğutmasız olduğu ve sayıların
        # doğal taşınımı anlattığı metinde geçmeli (doktrin 1).
        assert 'UNCOOLED' in k['message']
        assert 'natural convection' in k['message']

    @pytest.mark.parametrize('bos', [None, '', '   '])
    def test_bos_deger_de_gonderilmedi_sayilir(self, client, bos):
        g = client.post('/calculate',
                        json=dict(HIBRIT, cooling_channels=bos)).get_json()
        assert _kunye(g, 'cooling_channels') is not None, (
            f'{bos!r} "gönderilmedi" sayılıp varsayılan uygulanıyor ama '
            f'künye doğmuyor — sessiz düşüş bu kapıdan geri sızar.')

    @pytest.mark.parametrize('yol', HIBRIT_UCLAR)
    @pytest.mark.parametrize('secim', ['none', 'radial'])
    def test_kullanicinin_secimi_kunye_URETMEZ(self, client, yol, secim):
        """Kullanıcı seçtiyse beyan edilecek bir kabul YOKTUR."""
        g = client.post(yol,
                        json=dict(HIBRIT, cooling_channels=secim)).get_json()
        assert _kunye(g, 'cooling_channels') is None, (
            f'{yol}: kullanıcı {secim!r} seçti, künye yine de doğdu — '
            f'beyan yalan söylüyor.')


#: Alanı KABUL EDEN hibrit uçları (ÖH D27 / OH-D26-05).
#: ``/api/transient-analysis`` bu listeden ÇIKTI: o uçta soğutma seçimi
#: yayımlanan hiçbir sayıya girmediği ölçüldü (``docs/scofield/raw/OH/D27/
#: hibrit/a1/once.json`` K2: none / radial / spiral / regenerative dört
#: gövde BİT-AYNI, 0/3238 yaprak) ve alan artık fail-closed reddediliyor
#: (HTTP 422 ``unread_field``). Yani orada "gönderilen 'none' ile
#: gönderilmeyen alan arasındaki fark yalnız künyedir" cümlesi artık
#: KURULAMAZ — alan gönderilemez. Aşağıdaki üçüncü iddia o ucun yeni
#: sözleşmesini ADIYLA ölçer, böylece kapsam DARALMAZ.
HIBRIT_ALANI_KABUL_EDEN_UCLAR = ('/calculate', '/api/quick-geometry')


class TestHibritAyirtEdilebilirlik:
    """Onarım AYIRT EDİLEBİLİRLİK getirdi, SAYI OYNATMADI."""

    @pytest.mark.parametrize('yol', HIBRIT_ALANI_KABUL_EDEN_UCLAR)
    def test_iki_govde_artik_ayirt_edilebilir(self, client, yol):
        yok = client.post(yol, json=dict(HIBRIT)).get_json()
        acik = client.post(
            yol, json=dict(HIBRIT, cooling_channels='none')).get_json()
        assert _sha(yok) != _sha(acik), (
            f'{yol}: alanı göndermeyen gövde ile açıkça "none" seçen gövde '
            f'HÂLÂ bit-aynı — kabul ile seçim ayırt edilemiyor.')

    @pytest.mark.parametrize('yol', HIBRIT_ALANI_KABUL_EDEN_UCLAR)
    def test_fark_YALNIZ_kunyedir_fizik_oynamadi(self, client, yol):
        """Künye çıkarılınca iki gövde BİT-AYNI: hiçbir sayı kaymadı."""
        yok = client.post(yol, json=dict(HIBRIT)).get_json()
        acik = client.post(
            yol, json=dict(HIBRIT, cooling_channels='none')).get_json()
        ya, yb = _yapraklar(yok), _yapraklar(acik)
        fark = sorted(k for k in set(ya) | set(yb) if ya.get(k) != yb.get(k))
        assert fark, 'fark yok — üstteki bekçi zaten kırmızı olmalıydı'
        assert all(k.startswith('defaults_applied') for k in fark), (
            f'{yol}: künye DIŞINDA da fark var, yani onarım sayı oynattı: '
            f'{[k for k in fark if not k.startswith("defaults_applied")][:8]}')

    def test_transient_ucu_alani_artik_kabul_etmiyor(self, client):
        """ÖH D27 / OH-D26-05 — üçüncü uç kapsamdan DÜŞMEDİ, ÇEVRİLDİ.

        D26'da bu uç yukarıdaki iki iddiaya dahildi ve künye orada da
        doğuyordu; ama künyenin altındaki KABUL sonuçsuzdu (0/3238
        yaprak). D27 kabulü kaldırdı: alan gönderilirse hiçbir eğri
        yayımlanmaz, alan ADIYLA reddedilir. Alan gönderilmediğinde ise
        künye AYNEN doğar — ÖK-19 borcu geri açılmadı.
        """
        r = client.post('/api/transient-analysis',
                        json=dict(HIBRIT, cooling_channels='none'))
        assert r.status_code == 422, (
            f'/api/transient-analysis cooling_channels="none" için HTTP '
            f'{r.status_code} döndü; yayımlanan hiçbir sayıya girmeyen alan '
            'kabul edilemez (OH-D26-05)')
        g = r.get_json() or {}
        assert g.get('error') == 'unread_field', g.get('error')
        # Alan YOKSA sözleşme D26'daki gibi: 200 + künye.
        yok = client.post('/api/transient-analysis', json=dict(HIBRIT))
        assert yok.status_code == 200
        assert _kunye(yok.get_json(), 'cooling_channels') is not None, (
            'alan gönderilmeyen gövdede ÖH D26 künyesi kayboldu (ÖK-19)')

    @pytest.mark.parametrize('yol,en_az', [('/calculate', 400),
                                           ('/api/quick-geometry', 120)])
    def test_secim_hala_sonuc_belirliyor(self, client, yol, en_az):
        """Kabul sonuçsuz DEĞİL: ``none`` ⟷ ``radial`` yüzlerce yaprak.

        Ölçüldü: ``/calculate`` 460, ``/api/quick-geometry`` 153 yaprak.
        Bu sayı çökerse beyan anlamsızlaşır (beyan edilen kabul artık bir
        şey belirlemiyor demektir) — bekçi o çöküşü görür.
        """
        a = client.post(
            yol, json=dict(HIBRIT, cooling_channels='none')).get_json()
        b = client.post(
            yol, json=dict(HIBRIT, cooling_channels='radial')).get_json()
        ya, yb = _yapraklar(a), _yapraklar(b)
        fark = [k for k in set(ya) | set(yb) if ya.get(k) != yb.get(k)]
        assert len(fark) >= en_az, (
            f'{yol}: soğutma seçimi yalnız {len(fark)} yaprak oynatıyor '
            f'(ölçülen taban: en az {en_az}).')


class TestHibritTekKaynak:
    """Varsayılan, ÜRÜNÜN KENDİ menüsünden gelir (doktrin 4)."""

    def test_varsayilan_advanced_html_menusunun_ilk_secenegidir(self):
        assert HIBRIT_SOGUTMA_VARSAYILANI == _hibrit_menunun_ilk_secenegi(), (
            'app.py varsayılanı ile advanced.html menüsünün ilk seçeneği '
            'ayrıştı: kullanıcının gördüğü menü ile sunucunun uyguladığı '
            'kabul artık farklı.')

    def test_uc_govdelerinde_elle_yazili_none_kalmadi(self):
        """Üç uç da varsayılanı sabitten okur; dize gövdede YAZILMAZ."""
        metin = open(APP_PY, encoding='utf-8').read()
        agac = ast.parse(metin)
        suclu = []
        for dugum in ast.walk(agac):
            if not (isinstance(dugum, ast.Call)
                    and isinstance(dugum.func, ast.Name)
                    and dugum.func.id == '_hibrit_sogutma_secimi'):
                continue
            for arg in list(dugum.args) + [k.value for k in dugum.keywords]:
                if isinstance(arg, ast.Constant) and arg.value == 'none':
                    suclu.append(dugum.lineno)
        assert not suclu, (
            f'``none`` dizesi çağrı yerinde elle yazılı (satır {suclu}) — '
            f'tek kaynak bozuldu.')


class TestHibritKunyeSozlesmesi:
    """Künye, ucun ZATEN yayımladığı listeye AYNI biçimde biner."""

    def test_liste_arkadasiyla_ayni_bicim(self, client):
        """``chamber_pressure`` künyesi ile anahtar kümesi ortak olmalı."""
        g = client.post('/calculate', json={
            k: v for k, v in HIBRIT.items() if k != 'chamber_pressure'
        }).get_json()
        pc = _kunye(g, 'chamber_pressure')
        cc = _kunye(g, 'cooling_channels')
        assert pc is not None and cc is not None, (
            'iki kabul de yapıldı, ikisi de aynı listede beyan edilmeli')
        ortak = {'field', 'value', 'reason', 'message'}
        assert ortak <= set(pc) and ortak <= set(cc), (
            'aynı listede iki farklı künye biçimi var — tüketici '
            'elemanları tek sözleşmeyle okuyamaz.')
        assert cc['reason'] == pc['reason'] == 'not_supplied'

    def test_yeni_yanit_anahtari_dogmadi(self, client):
        """Künye MEVCUT ``defaults_applied`` kanalına biner."""
        yok = client.post('/calculate', json=dict(HIBRIT)).get_json()
        acik = client.post(
            '/calculate', json=dict(HIBRIT,
                                    cooling_channels='none')).get_json()
        yeni = set(yok) - set(acik)
        # ÖH D32 / OH-D31-13 — ÖLÇÜT ALANA BAĞLANDI (bekçi çevirisi).
        # Eski ölçüt ``yeni == {'defaults_applied'}`` idi ve ÖRTÜK bir
        # önermeye dayanıyordu: "açık gövdede defaults_applied HİÇ YOK".
        # O önerme, ucun geri kalan 18 ÖK-21 alanındaki SESSİZLİĞİNDEN
        # geliyordu (ölçüldü: ``D32/app-api-uc/a1/once.json`` K2 — künyede
        # anılan alan 1, sessiz yedek 23). Sessizlik bittiği için iki gövde
        # de künye taşıyor; İDDİA ise aynen duruyor ve burada ADIYLA
        # ölçülüyor: (a) hiçbir YENİ üst-düzey anahtar doğmadı,
        # (b) cooling_channels kabulü GERÇEKTEN o kanalda beyan ediliyor.
        assert yeni <= {'defaults_applied'}, (
            f'kabul beyanı yeni üst-düzey anahtar doğurdu: {yeni}')
        assert _kunye(yok, 'cooling_channels') is not None, (
            'alan gönderilmedi ama kabul defaults_applied kanalında '
            'beyan edilmiyor')
        assert _kunye(acik, 'cooling_channels') is None, (
            'kullanıcı seçimi gönderildiği hâlde uç "varsayılana düştüm" '
            'diyor')

    def test_ret_govdesi_varsayilan_bildirmez(self, client):
        r = client.post('/calculate',
                        json=dict(HIBRIT, cooling_channels='banana'))
        assert r.status_code == 422
        assert 'defaults_applied' not in (r.get_json() or {}), (
            'reddedilen istekte hiçbir şey çözülmedi; beyan edilecek '
            'uygulanmış varsayılan da yoktur.')


class TestHibritKapiAyakta:
    """ÖK-22: sağlıklı envanter gevşetilemez — kapı yerinde duruyor."""

    @pytest.mark.parametrize('deger', ['ablative', 'film_cooling', 'banana',
                                       0, True, ['radial']])
    def test_taninmayan_deger_hala_422(self, client, deger):
        r = client.post('/calculate',
                        json=dict(HIBRIT, cooling_channels=deger))
        assert r.status_code == 422, (
            f'{deger!r} artık 200 alıyor — D25 kapısı gevşedi (ÖK-22).')
        assert r.get_json()['error'] == 'unsupported_cooling_type'

    def test_menunun_HER_secenegi_motorda_cozuluyor(self):
        """Şablon ⟷ motor zinciri: menüye ölü seçenek eklenirse kırar."""
        from hrma.app import COOLING_CHANNEL_TO_TYPE
        metin = open(ADVANCED_HTML, encoding='utf-8').read()
        m = re.search(r'<select\s+id="cooling_channels"[^>]*>(.*?)</select>',
                      metin, re.S)
        secenekler = re.findall(r'<option\s+value="([^"]*)"', m.group(1))
        olu = [x for x in secenekler
               if x.strip().lower() not in COOLING_CHANNEL_TO_TYPE]
        assert not olu, (
            f'cooling_channels menüsünde motorun çözemediği seçenek: {olu}')
