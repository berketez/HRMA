# -*- coding: utf-8 -*-
"""ÖH D31 / altyapi a1 — belge ve kılavuz KAYIT bekçileri.

Kalemler: OH-Z5-05 (çapa borcu belgesi), OH-D21-07 (açılış rozeti),
OH-D21-12 (``/api/find-optimum-of`` bandı + gama bandı), OH-D22-07 (chug
ataleti + kademeli pompa), OH-D22-09 (``/api/fea/thermal`` reddi).

Bu kulvarın işi ÜRÜNÜ değiştirmek değil, önceki dalgalarda yayımlanmış
DAVRANIŞ DEĞİŞİKLİKLERİNİ kullanıcıya giden yüzeye (changelog 2.6.27 +
kılavuz TR/EN) yazmaktı. Bu yüzden bekçilerin üç türü var:

1. ÜRÜN BAĞI olan bekçiler: beyandaki sayı/hüküm, ürünün BUGÜNKÜ
   davranışıyla karşılaştırılır (uç çağrısı ya da tek-kaynak sabiti). Beyan
   ile ürün ayrışırsa kırmızı olur.
2. BEYAN bekçileri: ağır motor koşumu gerektiren sayılar (chug frekansı,
   pompa basma basıncı) için beyanın varlığı ve ölçülen sayının birebir
   yazıldığı denetlenir; ürün bağı yoktur (gerekçe: her koşum üç motorluk
   çözüm demektir, bekçi dosyası bunu taşıyamaz).
3. BORÇ İMİ: kılavuz PDF ikizi ayrışmış durumda; im ``xfail(strict)``tir ve
   kılavuz dalgası ikisini de yeniden ürettiğinde XPASS ile kendini söker.

Ters mutasyon kanıtı:
``docs/scofield/raw/OH/D31/altyapi/a1/mutasyon.json``.
Ölçüm: ``docs/scofield/raw/OH/D31/altyapi/a1/{olcum.py,once.json,sonra.json}``.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D31',
                     'altyapi', 'a1')


def _oku(bagil):
    with open(os.path.join(KOK, bagil), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def surum_notu():
    """changelog.json 2.6.27 kaydı (notes_en + notes_tr)."""
    d = json.loads(_oku('hrma/data/changelog.json'))
    # karar §28-19/§28-46: yayımlanmamış 2.6.27 kaydı 3.0.0 adıyla çıkar.
    return [v for v in d['versions'] if v['version'] == '3.0.0'][0]


@pytest.fixture(scope='module')
def kilavuzlar():
    return {
        'tr': _oku('docs/user_guide/HRMA-Kullanma-Kilavuzu-TR.tex'),
        'en': _oku('docs/user_guide/HRMA-User-Guide-EN.tex'),
    }


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(istemci, yol, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            r = istemci.post(yol, json=govde)
    return r.status_code, (r.get_json() or {})


# ===========================================================================
# OH-D21-12 — /api/find-optimum-of bant reddi: BEYAN ile ÜRÜN aynı mı?
# ===========================================================================

def test_ohd2112_find_optimum_reddi_urunle_ayni(istemci, surum_notu):
    """Beyan edilen ret (422 + ``invalid_chamber_pressure``) ürüne bağlıdır.

    ÖLÇÜLDÜ (``once.json`` -> ``OH-D21-12_find_optimum``, taban
    ``9d70e9ed``): ``chamber_pressure`` 0 ve -20 için HTTP 422,
    ``error_code='invalid_chamber_pressure'``,
    ``invalid_fields[0].field='chamber_pressure'``,
    ``reason='out_of_range'``; sağlıklı 20 bar HTTP 200 ve
    ``max_isp=232.69943859344866``. Kalem OH-D21-12 bu değişikliğin
    BELGE borcuydu (D21 app-api a2 riskleri).
    """
    for pc in (0, -20):
        durum, govde = _post(istemci, '/api/find-optimum-of', {
            'motor_type': 'hybrid', 'fuel': 'htpb', 'oxidizer': 'n2o',
            'chamber_pressure': pc})
        assert durum == 422, pc
        assert govde.get('error_code') == 'invalid_chamber_pressure', pc
        alanlar = [f.get('field') for f in (govde.get('invalid_fields') or [])]
        assert 'chamber_pressure' in alanlar, pc

    for notlar in (surum_notu['notes_en'], surum_notu['notes_tr']):
        assert '/api/find-optimum-of' in notlar
        assert 'invalid_chamber_pressure' in notlar
        assert 'chamber_pressure' in notlar
        assert '422' in notlar


def test_ohd2112_gama_bandi_beyanla_tek_kaynak(surum_notu, kilavuzlar):
    """Kılavuz ve changelog'daki gama bandı, MODÜLÜN sabitiyle aynı sayıdır.

    ÖLÇÜLDÜ (``once.json`` -> ``OH-D21-12_gamma``): ``GAMMA_BAND_MIN=1.05``,
    ``GAMMA_BAND_MAX=1.67``, ``GAMMA_REPO_DEFAULT=1.2``; 1,02 ve 3,00
    ``ValueError`` ile reddediliyor, 1,25 aynen geçiyor. Bekçi beyanı
    sabite bağlar: bant kodda değişirse belge kırmızıya döner (ÖK-04 tek
    kaynak).
    """
    from hrma.analysis import heat_transfer_analysis as hta

    alt = repr(float(hta.GAMMA_BAND_MIN))      # '1.05'
    ust = repr(float(hta.GAMMA_BAND_MAX))      # '1.67'
    varsayilan = repr(float(hta.GAMMA_REPO_DEFAULT))  # '1.2'
    tr_alt, tr_ust = alt.replace('.', ','), ust.replace('.', ',')

    en = surum_notu['notes_en']
    tr = surum_notu['notes_tr']
    assert alt in en and ust in en
    assert tr_alt in tr and tr_ust in tr
    assert 'gamma_source: repo_default' in en
    assert 'gamma_source: repo_default' in tr
    # Depo varsayılanı belgede 1,20 olarak yazılır (kodda 1.2).
    assert varsayilan.rstrip('0').rstrip('.') == '1.2'
    assert '1.20' in en and "1,20" in tr

    assert alt in kilavuzlar['en'] and ust in kilavuzlar['en']
    assert tr_alt in kilavuzlar['tr'] and tr_ust in kilavuzlar['tr']


# ===========================================================================
# OH-D22-09 — /api/fea/thermal reddi 422/501: BEYAN ile ÜRÜN aynı mı?
# ===========================================================================

def test_ohd2209_fea_thermal_reddi_urunle_ayni(istemci, surum_notu):
    """Red artık HTTP 200 ile gelmiyor; beyan bunu söylüyor.

    ÖLÇÜLDÜ (``once.json`` -> ``OH-D22-09_fea_thermal``): iki red vakası da
    HTTP 422 + üst düzey ``status='not_modelled'`` (eskiden HTTP 200 +
    ``status='success'`` iken ``fea.status='NOT_MODELLED'``).
    """
    for govde_istek in ({'motor_results': {'chamber_pressure': 20.0}},
                        {'motor_results': {'chamber_pressure': 20.0},
                         'axial_profile': {'x_m': [], 'T_recovery_K': [],
                                           'h_g_W_m2K': []}}):
        durum, govde = _post(istemci, '/api/fea/thermal', govde_istek)
        assert durum == 422
        assert govde.get('status') == 'not_modelled'

    for notlar in (surum_notu['notes_en'], surum_notu['notes_tr']):
        assert '/api/fea/thermal' in notlar
        assert 'not_modelled' in notlar
        assert '422' in notlar and '501' in notlar
        assert 'NOT_AVAILABLE' in notlar and 'INPUTS_READY' in notlar


# ===========================================================================
# OH-D21-07 — açılış rozeti: BEYAN ile ŞABLON aynı mı?
# ===========================================================================

def test_ohd2107_rozet_bilinmeyen_durumla_dogar(surum_notu, kilavuzlar):
    """ÇEVRİLDİ (v3.0.1 K kulvarı, Ayberk tur 1): rozet SÖKÜLDÜ.

    Eski hâli üç şablonda ``status-unknown`` rozetini ŞART koşuyordu.
    ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ayberk1/kaynak-cea/gorsel_once.json,
    gerçek tarayıcı): rozet "denetlenmedi" diye doğuyor ama yoklamadan sonra
    HER makinede "NASA CEA OFFLINE / NIST WEBBOOK OFFLINE" diyordu (CEA kolu
    DAİMA 'local', NIST ayrıştırıcısı HİÇ eşleşmiyor) ve hiçbir sayının
    kaynağı değildi. Şablon tarafı artık rozetin YOKLUĞUNU ölçer.

    3.0.0 sürüm notu (yayımlanmış, tarihsel kayıt) rozetin o sürümdeki
    davranışını anlatır ve DEĞİŞMEZ. Kılavuzların güncellenmesi bu kulvarın
    dosyası değildir: aşağıdaki ``test_kilavuz_rozet_metni_devirde`` borcu
    xfail(strict) ile adıyla taşır.
    """
    for sayfa in ('advanced.html', 'solid.html', 'liquid.html'):
        metin = _oku(os.path.join('hrma', 'templates', sayfa))
        assert not re.search(r'class="[^"]*\b(?:database-status|cea-status|nist-status)\b', metin), sayfa
        assert 'class="data-source-line"' in metin, sayfa

    assert 'not checked yet' in surum_notu['notes_en']
    assert 'henüz denetlenmedi' in surum_notu['notes_tr']


def test_kilavuz_rozet_metni_devirde(kilavuzlar):
    """Kılavuzlar sökülen veritabanı rozetini anlatmıyor (borç ÖDENDİ).

    V301/BELGE (27 Eki 2026, sürüm 3.0.5): rozet anlatımı EN + TR kılavuzda
    veri kaynağı satırı + NASA CEA karşılaştırma bloğuyla değiştirildi; test
    geçti ve ``xfail(strict=True)`` imi kaldırıldı. Bekçinin kendisi durur:
    rozet metni kılavuza geri dönerse kırmızıdır.
    """
    assert 'not checked yet' not in kilavuzlar['en']
    assert 'henüz denetlenmedi' not in kilavuzlar['tr'].replace('\n', ' ')


# ===========================================================================
# OH-D22-07 — chug ataleti + kademeli pompa: BEYAN bekçisi (ürün bağı yok)
# ===========================================================================

def test_ohd2207_chug_ve_pompa_sayilari_beyanda(surum_notu, kilavuzlar):
    """Ölçülen üç sayı changelog'a BİREBİR yazıldı.

    ÖLÇÜLDÜ (``once.json`` -> ``OH-D22-07_chug`` / ``OH-D22-07_pompa``,
    taban ``9d70e9ed``): 25 kN LOX/RP-1, 60 bar, O/F 2,2 motorunda
    ``feed_line_length_m`` yokken ``unstable`` / 77.43027880630987 Hz
    (``inertance_included`` yanlış), 2,5 m ile ``stable`` /
    33.57814011538745 Hz (``inertance_included`` doğru); 250 kN LOX/CH4,
    150 bar kademeli yanmada ``required_pump_discharge_bar`` =
    186.33976123548217 (önceki derleme 283,996 yayımlıyordu — D22 ölçümü,
    ``docs/scofield/raw/OH/D22/sivi/a1/``).

    Ürün bağı YOK: bağlamak üç motorluk çözüm koşturmak demektir; bu bekçi
    yalnız beyanın ölçülen sayıyı taşıdığını güvenceye alır.
    """
    en, tr = surum_notu['notes_en'], surum_notu['notes_tr']
    for sayi in ('77.43027880630987', '33.57814011538745',
                 '186.33976123548217'):
        assert sayi in en, sayi
        assert sayi.replace('.', ',') in tr, sayi
    for anahtar in ('feed_line_length_m', 'inertance_included',
                    'required_pump_discharge_bar'):
        assert anahtar in en and anahtar in tr, anahtar
    assert '283.996' in en and '283,996' in tr
    # Kılavuz kullanıcıya dönüktür: alan adı değil, yuvarlanmış sayı.
    assert '77,4 Hz' in kilavuzlar['tr'] and '33,6 Hz' in kilavuzlar['tr']
    assert '77.4 Hz' in kilavuzlar['en'] and '33.6 Hz' in kilavuzlar['en']


# ===========================================================================
# OH-Z5-05 — çapa borcu belgesi ve kapanış aracı
# ===========================================================================

def test_ohz505_capa_borcu_belgesi_cakili():
    """Borç belgesi, ADLI referans çapayı ve kapanış ölçütünü taşıyor.

    ÖLÇÜLDÜ (``capa_once_taban.json`` / ``capa_taban_ozet.json``, D31 tabanı
    ``9d70e9ed``, ortak taban ağacında): hibrit 37.086 / katı 4.611 / sıvı
    4.421 yaprak. Fable ŞART-2 (Z5, 27 Ağu 2026) çapanın app.py kulvarı
    kapanınca YENİDEN alınmasını istiyor; koşul bu dalgada oluşmadı, borç
    belgeye çivilendi.
    """
    belge = _oku(kanit_gerekli(os.path.join('docs', 'scofield', 'raw', 'OH', 'D31',
                              'altyapi', 'a1', 'capa_borcu_belgesi.md')))
    ozet = json.loads(_oku(kanit_gerekli(os.path.join(
        'docs', 'scofield', 'raw', 'OH', 'D31', 'altyapi', 'a1',
        'capa_taban_ozet.json'))))
    assert len(ozet) == 3
    for motor, kayit in ozet.items():
        assert kayit['sha256'][:16] in belge, motor
        # Yaprak sayısı belgede binlik ayırıcıyla yazılır (37.086).
        n = kayit['yaprak']
        assert ('%d.%03d' % (n // 1000, n % 1000)) in belge, motor
    assert 'capa_kiyas.py' in belge
    assert 'ŞART-2' in belge
    # Borç, kaldırıldığı yerden de görünür olmalı (Z5 denetim dizini).
    okubeni = _oku(kanit_gerekli(os.path.join('docs', 'scofield', 'raw', 'OH', 'Z5',
                                'denetim', 'OKUBENI.md')))
    assert 'capa_borcu_belgesi.md' in okubeni


def test_ohz505_kiyas_araci_sapan_yapragi_goruyor(tmp_path):
    """Kapanış aracı gerçekten sapma görüyor (aksi hâlde borç kapanışı sahte).

    Araç ``capa_kiyas.py``, Z5 ``d20`` biçimini üretir: motor başına
    kaybolan/yeni/DEGISEN. Bu bekçi aracı SENTETİK iki çapayla sınar; ürün
    koşumu gerektirmez.
    """
    yol = os.path.join(KANIT, 'capa_kiyas.py')
    spec = importlib.util.spec_from_file_location('d31_capa_kiyas', kanit_gerekli(yol))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    a = {'A_gecerli_govde': {'A1': {'sha256': 'aa', 'govde': {
        'isp': '232.0', 'blok': {'x': '1'}}}}}
    b = {'A_gecerli_govde': {'A1': {'sha256': 'bb', 'govde': {
        'isp': '999.0', 'blok': {'x': '1'}, 'yeni': '3'}}}}
    pa = tmp_path / 'a.json'
    pb = tmp_path / 'b.json'
    pa.write_text(json.dumps(a), encoding='utf-8')
    pb.write_text(json.dumps(b), encoding='utf-8')

    yapraklar = dict(mod.yapraklar(a['A_gecerli_govde']['A1']['govde']))
    assert set(yapraklar) == {'/isp', '/blok/x'}

    import subprocess
    import sys
    r = subprocess.run([sys.executable, kanit_gerekli(yol), str(pa), str(pb)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 1, r.stdout
    assert 'DEGISEN /isp' in r.stdout
    assert 'YENI /yeni' in r.stdout
    # Aynı dosya kendisiyle kıyaslanınca BİT-AYNI ve çıkış 0.
    r2 = subprocess.run([sys.executable, kanit_gerekli(yol), str(pa), str(pa)],
                        capture_output=True, text=True, timeout=120)
    assert r2.returncode == 0 and 'BIT-AYNI' in r2.stdout


# ===========================================================================
# OH-D31-03 / OH-D21-07 — kılavuz PDF ikizi tek kaynaktan üretilir (BORÇ ÖDENDİ)
# ===========================================================================

def test_kilavuz_ikizi_kaynaktan_uretilmis():
    """Uygulamanın açtığı kılavuz ile depo kopyası BİT-AYNI olmalı.

    ÖLÇÜLDÜ (D31 altyapi a1, pdf_ikiz.json): im konduğunda static kopya
    2.6.1, docs/user_guide kopyası 2.6.25, .tex kaynağı 2.6.26 metnini
    taşıyordu; kullanıcının açtığı kılavuz kaynaktan iki sürüm geriydi ve
    borç xfail(strict) imiyle duruyordu.

    ÖDENDİ (kılavuz dalgası, 16 Eylül 2026): TR ve EN kılavuzlar 2.6.27
    için baştan yazıldı, 20 ekran görüntüsü gerçek uygulamadan alındı ve
    iki kopya da ``tools/kilavuz_derle.sh`` ile TEK kaynaktan
    (docs/user_guide/*.tex) üretildi — md5'ler eşit. İm söküldü; bu bekçi
    artık ayrışmayı kırmızıyla bildirir. Yeniden üretim:
    ``tools/kilavuz_derle.sh`` (kontrol için ``--kontrol``).
    """
    for ad in ('HRMA-Kullanma-Kilavuzu-TR.pdf', 'HRMA-User-Guide-EN.pdf'):
        a = open(os.path.join(KOK, 'hrma', 'static', 'docs', ad), 'rb').read()
        b = open(os.path.join(KOK, 'docs', 'user_guide', ad), 'rb').read()
        assert hashlib.md5(a).hexdigest() == hashlib.md5(b).hexdigest(), ad
