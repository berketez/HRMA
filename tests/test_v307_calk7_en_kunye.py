"""3.0.7 — M7-CALK-7 kalanı (ONARIM2-ÇALK-SEKME devri; ana model 20 Kas).

ONARIM2-ÇALK-SEKME aktarım dosyasının insan okur metnini arayüz diline
çevirdi; İngilizce dosyada motor tanklarının eşdeğer model tablosu künyesi
(``slosh_analysis.silindir_tablosu``: "Denk.", "Tablo", "askı" …) ve motor
bağlamasının iki kaynak ifadesi ("debi × süre", "ateşleme anındaki doyma
yoğunluğu") Türkçe kalıyordu (ölçüm: onarim2-calk-sekme/c7_olcum.json, sıvı
oksitleyici EN JSON 1, doluluk CSV 5, zaman CSV 1 satır; hibrit N₂O 1+5+1).
Bekçi: EN aktarımın üç biçiminde künye satırlarında Türkçe harf ve Türkçe
kaynak kısaltması yok; TR aktarım aynı kalır.
"""
import json
import re

import pytest

from tests.test_v307_onarim2_calk_sekme import _aktar, _meta

_TRK = re.compile('[çğıöşüÇĞİÖŞÜ]')
_TR_KISALTMA = re.compile(r'\b(?:Denk\.|Tablo|Şekil|madde)\b')


@pytest.fixture(scope='module')
def sonuclar():
    from tests.test_v307_onarim_calk import _coz
    return {'liquid': _coz('liquid'), 'hybrid': _coz('hybrid')}


def _aktar_mt(sonuc, mt, bicim, dil, tank):
    import contextlib
    import io
    from hrma.app import app
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()):
        return app.test_client().post('/api/slosh-analysis/export', json={
            'tank_modeli': {'motor_type': mt, 'motor_sonucu': sonuc},
            'disa_aktarim': {'tank_id': tank, 'bicim': bicim, 'dil': dil}})


def _kunye_satirlari(bicim, metin):
    if bicim == 'json':
        d = json.loads(metin)
        return (list(d['kunye']) + list(d['esdeger_model_tablosu']['kunye'])
                + [d['zaman_ekseni']['kaynak'] or ''])
    return list(_meta(metin).get('kunye') or [])


EN_AKTARIM_VAKALARI = [('liquid', 'oksitleyici'), ('liquid', 'yakit'), ('hybrid', 'n2o')]


@pytest.mark.slow
@pytest.mark.parametrize("mt,tank", EN_AKTARIM_VAKALARI)
@pytest.mark.parametrize('bicim', ['json', 'csv_doluluk', 'csv_zaman'])
def test_en_aktarim_kunyesi_turkce_tasimaz(sonuclar, mt, tank, bicim):
    r = _aktar_mt(sonuclar[mt], mt, bicim, 'en', tank)
    assert r.status_code == 200, r.data[:300]
    satirlar = _kunye_satirlari(bicim, r.data.decode('utf-8'))
    assert satirlar
    turkce = [s for s in satirlar if _TRK.search(s) or _TR_KISALTMA.search(s)]
    assert not turkce, turkce


@pytest.mark.slow
def test_tr_aktarim_kunyesi_turkce_kalir(sonuclar):
    r = _aktar_mt(sonuclar['liquid'], 'liquid', 'json', 'tr', 'oksitleyici')
    satirlar = _kunye_satirlari('json', r.data.decode('utf-8'))
    birlesik = '\n'.join(satirlar)
    assert 'SP-8009 Tablo I' in birlesik and 'debi × süre' in birlesik
    assert 'Table I' not in birlesik


def test_ceviri_sozlugu_kaynak_satirlarla_eslesiyor():
    """Sözlüğün anahtarları üreticinin bugünkü satırlarıdır (satır değişirse
    çeviri sessizce düşmesin)."""
    from hrma.analysis import calkanti_arayuz as ca
    from hrma.analysis import slosh_analysis as sa
    from hrma.analysis.slosh_analysis import silindir_tablosu
    tablo = silindir_tablosu('oksitleyici', 0.2, 1.0, 900.0, 'LOX')
    kunye = tablo.sozluk()['kunye']
    assert ('I0: ' + sa.I0_KAYNAK_METNI) in kunye
    eslesmeyen = [s for s in kunye if (_TRK.search(s) or _TR_KISALTMA.search(s))
                  and s not in ca._EN_KUNYE_SATIRLARI]
    assert not eslesmeyen, eslesmeyen
