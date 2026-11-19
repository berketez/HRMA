# -*- coding: utf-8 -*-
"""V307 / FS-HARİTA-GÖRÜNTÜ: harita paketi görüntü bileşeni okuyucusu ve üretim aracının saf işlevleri.

Okuyucu (``hrma/analysis/map_pack_imagery.py``) saf Python + sqlite3'tür; burada:
gidiş-dönüş, kapsam/düzey dışı None, bozuk/şişirilmiş/kötü niyetli SQLite girdisinde ADLI ret,
WebP başlık kapısı, belirlenimcilik, zemin sağlayıcı sözleşmesi (FS-HARİTA-VERİ F2.4), Copernicus
atıf metni. Üretim aracının (``tools/harita_goruntu_uret.py``; rasterio'lu adımları üretim
venv'inde koşar) ağ ve GDAL gerektirmeyen işlevleri de sınanır.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import sqlite3
import struct

import numpy as np
import pytest
from PIL import Image

from hrma.analysis import map_pack_imagery as mpi
from hrma.analysis import tile_cache

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _arac():
    spec = importlib.util.spec_from_file_location(
        '_harita_goruntu_uret_test', os.path.join(DEPO, 'tools', 'harita_goruntu_uret.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope='module')
def arac():
    return _arac()


# ---------------------------------------------------------------------------
# Yardımcılar: gerçek WebP karolar ve geçerli bir kap
# ---------------------------------------------------------------------------

def _webp(karo_rgb=(40, 90, 60), boyut=512, alfa=None, kayipsiz=False) -> bytes:
    if alfa is None:
        im = Image.new("RGB", (boyut, boyut), karo_rgb)
    else:
        im = Image.new("RGBA", (boyut, boyut), karo_rgb + (255,))
        a = Image.new('L', (boyut, boyut), 255)
        a.paste(0, (0, 0, boyut, alfa))
        im.putalpha(a)
    bio = io.BytesIO()
    im.save(bio, 'WEBP', quality=80, lossless=kayipsiz)
    return bio.getvalue()


SAHNELER = [{'id': 'S2B_36TXL_20250626_0_L2A', 'datetime': '2025-06-26T08:35:00Z',
             'mgrs': 'MGRS-36TXL', 'cloud_cover': 0.1, 'pixel_share': 1.0}]
# Sinop yakınında bir z13 karosu ve ataları (ızgara tile_cache'ten).
Z13 = (13, *tile_cache.lonlat_to_tile(13, 35.1531, 42.0231))
# Görüntü alanı: Z13'ün z9 atasının kutusu (bütün test karolarını kapsar).
SINIR = tile_cache.tile_to_bbox(9, Z13[1] >> 4, Z13[2] >> 4)


def _duz_detail(m):
    """Fikstür için halkasız (bütün düzeyler kutunun tamamında) 'detail'."""
    try:
        zmax = int(m['zoom_max'])
        w, s_, e, n = (float(v) for v in m['bounds'].split(','))
    except (ValueError, KeyError):
        zmax, (w, s_, e, n) = 13, SINIR
    return json.dumps({'center': [(s_ + n) / 2, (w + e) / 2], 'full_zoom_max': zmax, 'rings': []})


def _meta(**degis):
    m = {'schema': mpi.SCHEMA, 'grid': mpi.GRID_ID, 'tile_px': str(mpi.TILE_PX),
         'format': 'webp', 'zoom_min': '9', 'zoom_max': '13',
         'bounds': ','.join('%.9f' % v for v in SINIR), 'pack_id': 'sinop_tr',
         'attribution': mpi.ATTRIBUTION_TEMPLATE.format(years='2025'),
         'license': mpi.LICENSE_ID, 'scenes': json.dumps(SAHNELER)}
    m.update(degis)
    if 'detail' not in degis:
        m['detail'] = _duz_detail(m)
    return {k: v for k, v in m.items() if v is not None}


def _kap(yol, karolar=None, meta=None, ddl=None, ek_sql=()):
    """karolar: {(z,x,y): (coverage, bayt)}"""
    if os.path.exists(yol):
        os.remove(yol)
    db = sqlite3.connect(yol)
    for d in (ddl or mpi.DDL):
        db.execute(d)
    for k, v in sorted((meta if meta is not None else _meta()).items()):
        db.execute('INSERT INTO metadata VALUES (?,?)', (k, v))
    for (z, x, y), (cov, b) in sorted((karolar or {}).items()):
        db.execute('INSERT INTO tiles VALUES (?,?,?,?,?)', (z, x, y, cov, b))
    for s in ek_sql:
        db.execute(s)
    db.commit()
    db.close()
    return str(yol)


def _atalar(z, x, y):
    return [(z - k, x >> k, y >> k) for k in range(0, 5)]


@pytest.fixture()
def gecerli(tmp_path):
    tam = _webp()
    kismi = _webp((10, 20, 200), alfa=100)
    karolar = {k: (10000, tam) for k in _atalar(*Z13)}
    z, x, y = Z13
    karolar[(13, x + 1, y)] = (8047, kismi)
    return _kap(tmp_path / 'g.sqlite', karolar), tam, kismi


# ---------------------------------------------------------------------------
# 1) Gidiş-dönüş, kapsam dışı, düzey dışı
# ---------------------------------------------------------------------------

def test_gidis_donus_ve_bilgi(gecerli):
    yol, tam, kismi = gecerli
    ok = mpi.GoruntuOkuyucu(yol)
    try:
        for k in _atalar(*Z13):
            assert ok.karo(*k) == tam
        z, x, y = Z13
        assert ok.karo(13, x + 1, y) == kismi
        assert ok.karo_bilgisi(13, x + 1, y) == (8047, len(kismi))
        assert ok.bilgi['pack_id'] == 'sinop_tr'
        assert ok.bilgi['zoom_min'] == 9 and ok.bilgi['zoom_max'] == 13
        assert ok.bilgi['scenes'][0]['id'] == SAHNELER[0]['id']
    finally:
        ok.kapat()


def test_kapsam_ve_duzey_disi_none(gecerli):
    yol, _t, _k = gecerli
    ok = mpi.GoruntuOkuyucu(yol)
    try:
        z, x, y = Z13
        assert ok.karo(13, x + 5, y + 5) is None            # kapta yok
        assert ok.karo(8, x >> 5, y >> 5) is None           # zoom_min altı
        assert ok.karo(14, 2 * x, 2 * y) is None            # zoom_max üstü (ata ayrı yol)
        assert ok.karo(13, -1, 0) is None                   # matris dışı
        mw, mh = tile_cache.matrix_size(13)
        assert ok.karo(13, mw, 0) is None and ok.karo(13, 0, mh) is None
        assert ok.karo(16, 0, 0) is None                    # okuyucu tavanı üstü
    finally:
        ok.kapat()


@pytest.mark.parametrize('kotu', [(13.0, 1, 1), ('13', 1, 1), (True, 1, 1), (13, None, 1),
                                  (13, 1, 2.5)])
def test_tamsayi_olmayan_koordinat_adli_ret(gecerli, kotu):
    ok = mpi.GoruntuOkuyucu(gecerli[0])
    try:
        with pytest.raises(mpi.GoruntuHatasi) as e:
            ok.karo(*kotu)
        assert e.value.kod == 'bad_tile_coord'
    finally:
        ok.kapat()


def test_belirlenimcilik_ayni_bayt(gecerli, tmp_path):
    yol, _t, _k = gecerli
    a = [mpi.GoruntuOkuyucu(yol) for _ in range(2)]
    try:
        for k in _atalar(*Z13):
            assert a[0].karo(*k) == a[1].karo(*k)
    finally:
        for o in a:
            o.kapat()
    # Aynı içerikle iki kez kurulan kap bayt bayt aynı (sıralı yazım)
    karolar = {k: (10000, _webp()) for k in _atalar(*Z13)}
    h = [hashlib.sha256(open(_kap(tmp_path / ('d%d.sqlite' % i), karolar), 'rb').read()).hexdigest()
         for i in range(2)]
    assert h[0] == h[1]


def test_ata_penceresi(gecerli):
    ok = mpi.GoruntuOkuyucu(gecerli[0])
    try:
        z, x, y = Z13
        a = ok.karo_veya_ata(15, 4 * x + 3, 4 * y + 1)
        assert (a.z, a.x, a.y, a.dz) == (13, x, y, 2)
        assert a.pencere == (3 * 128, 1 * 128, 128)
        assert ok.karo_veya_ata(15, 4 * x + 3, 4 * y + 1, en_fazla=1) is None
        b = ok.karo_veya_ata(*Z13)
        assert b.dz == 0 and b.pencere == (0, 0, 512) and b.coverage == 10000
        with pytest.raises(mpi.GoruntuHatasi):          # tavan MAX_UPSAMPLE_LEVELS (4)
            ok.karo_veya_ata(15, 0, 0, en_fazla=mpi.MAX_UPSAMPLE_LEVELS + 1)
    finally:
        ok.kapat()


# ---------------------------------------------------------------------------
# 2) Bozuk / şişirilmiş / kötü niyetli dosya: ADLI ret
# ---------------------------------------------------------------------------

def _kod(yol):
    with pytest.raises(mpi.GoruntuHatasi) as e:
        mpi.GoruntuOkuyucu(str(yol))
    return e.value.kod


def test_dosya_yok_bos_ve_sqlite_degil(tmp_path):
    assert _kod(tmp_path / 'yok.sqlite') == 'imagery_missing'
    (tmp_path / 'bos.sqlite').write_bytes(b'')
    assert _kod(tmp_path / 'bos.sqlite') == 'bad_imagery_file'
    (tmp_path / 'metin.sqlite').write_bytes(b'<html>404</html>' * 100)
    assert _kod(tmp_path / 'metin.sqlite') == 'bad_imagery_file'
    os.mkdir(tmp_path / 'dizin.sqlite')
    assert _kod(tmp_path / 'dizin.sqlite') == 'imagery_missing'


def test_kesik_sqlite_adli_ret(gecerli, tmp_path):
    ham = open(gecerli[0], 'rb').read()
    (tmp_path / 'kesik.sqlite').write_bytes(ham[:len(ham) // 3])
    with pytest.raises(mpi.GoruntuHatasi) as e:
        ok = mpi.GoruntuOkuyucu(str(tmp_path / 'kesik.sqlite'))
        for k in _atalar(*Z13):
            ok.karo(*k)
    assert e.value.kod in ('bad_imagery_file', 'bad_imagery_schema', 'bad_imagery_meta')


def test_sayfa_bozulmasi_adli_ret(gecerli, tmp_path):
    ham = bytearray(open(gecerli[0], 'rb').read())
    for i in range(4096 + 16, len(ham), 97):           # başlık dışındaki her şeyi boz
        ham[i] ^= 0x5A
    (tmp_path / 'bozuk.sqlite').write_bytes(bytes(ham))
    with pytest.raises(mpi.GoruntuHatasi) as e:
        ok = mpi.GoruntuOkuyucu(str(tmp_path / 'bozuk.sqlite'))
        for k in _atalar(*Z13):
            ok.karo(*k)
    assert e.value.kod in ('bad_imagery_file', 'bad_imagery_schema', 'bad_imagery_meta',
                           'bad_tile')


def test_boyut_tavani(tmp_path, monkeypatch, gecerli):
    monkeypatch.setattr(mpi, 'MAX_FILE_BYTES', 1024)
    assert _kod(gecerli[0]) == 'imagery_too_large'


@pytest.mark.parametrize('ek', [
    'CREATE TABLE fazla (a)',
    'CREATE VIEW v AS SELECT 1',
    'CREATE INDEX ix ON tiles (coverage)',
    'CREATE TRIGGER t AFTER INSERT ON metadata BEGIN SELECT 1; END',
])
def test_fazla_sema_nesnesi_ret(tmp_path, ek):
    assert _kod(_kap(tmp_path / 'f.sqlite', ek_sql=[ek])) == 'bad_imagery_schema'


def test_gorunum_tablo_yerine_ret(tmp_path):
    ddl = (mpi.DDL[0], 'CREATE TABLE gercek (z, x, y, coverage, data)',
           'CREATE VIEW tiles AS SELECT * FROM gercek')
    db = sqlite3.connect(str(tmp_path / 'v.sqlite'))
    for d in ddl:
        db.execute(d)
    for k, v in _meta().items():
        db.execute('INSERT INTO metadata VALUES (?,?)', (k, v))
    db.commit()
    db.close()
    assert _kod(tmp_path / 'v.sqlite') == 'bad_imagery_schema'


def test_sutun_tanimi_farkli_ret(tmp_path):
    ddl = (mpi.DDL[0], 'CREATE TABLE tiles (z INTEGER NOT NULL, x INTEGER NOT NULL, '
           'y INTEGER NOT NULL, coverage INTEGER NOT NULL, data TEXT NOT NULL, '
           'PRIMARY KEY (z, x, y)) WITHOUT ROWID')
    assert _kod(_kap(tmp_path / 's.sqlite', ddl=ddl)) == 'bad_imagery_schema'


@pytest.mark.parametrize('degis,kod', [
    ({'schema': 'hrma.map_pack_imagery/1'}, 'bad_imagery_schema'),   # 16-17 Kas paketleri
    ({'schema': 'hrma.map_pack_imagery/3'}, 'bad_imagery_schema'),
    ({'detail': None}, 'bad_imagery_meta'),
    ({'detail': '{bozuk'}, 'bad_imagery_meta'),
    ({'detail': json.dumps({'center': [0.0, 0.0], 'full_zoom_max': 13, 'rings': []})},
     'bad_imagery_meta'),                                            # merkez kutu dışında
    ({'detail': json.dumps({'center': [42.0, 35.2], 'full_zoom_max': 11,
                            'rings': [{'zoom': 12, 'radius_km': 50.0}]})}, 'bad_imagery_meta'),
    ({'detail': json.dumps({'center': [42.0, 35.2], 'full_zoom_max': 11,
                            'rings': [{'zoom': 12, 'radius_km': 25.0},
                                      {'zoom': 13, 'radius_km': 50.0}]})}, 'bad_imagery_meta'),
    ({'detail': json.dumps({'center': [42.0, 35.2], 'full_zoom_max': 11,
                            'rings': [{'zoom': 13, 'radius_km': 50.0},
                                      {'zoom': 12, 'radius_km': 25.0}]})}, 'bad_imagery_meta'),
    ({'detail': json.dumps({'center': [42.0, 35.2], 'full_zoom_max': 11,
                            'rings': [{'zoom': 12, 'radius_km': 'nan'},
                                      {'zoom': 13, 'radius_km': 25.0}]})}, 'bad_imagery_meta'),
    ({'detail': json.dumps({'center': [42.0, 35.2], 'full_zoom_max': 8, 'rings': []})},
     'bad_imagery_meta'),
    ({'grid': 'webmercator'}, 'bad_imagery_meta'),
    ({'tile_px': '256'}, 'bad_imagery_meta'),
    ({'format': 'png'}, 'bad_imagery_meta'),
    ({'zoom_min': '14', 'zoom_max': '13'}, 'bad_imagery_meta'),
    ({'zoom_max': '16'}, 'bad_imagery_meta'),
    ({'zoom_max': 'on uc'}, 'bad_imagery_meta'),
    ({'bounds': '35,41,34,42'}, 'bad_imagery_meta'),
    ({'bounds': 'nan,41,35,42'}, 'bad_imagery_meta'),
    ({'bounds': '1,2,3'}, 'bad_imagery_meta'),
    ({'pack_id': '../etc'}, 'bad_imagery_meta'),
    ({'scenes': '[]'}, 'bad_imagery_meta'),
    ({'scenes': '{bozuk'}, 'bad_imagery_meta'),
    ({'attribution': None}, 'bad_imagery_meta'),
    ({'license': 'x' * 401}, 'bad_imagery_meta'),
])
def test_metadata_kapilari(tmp_path, degis, kod):
    assert _kod(_kap(tmp_path / 'm.sqlite', meta=_meta(**degis))) == kod


def test_metadata_sisirilmis(tmp_path):
    m = _meta(scenes=json.dumps(SAHNELER + [{'id': 'x' * 300000, 'datetime': 'y'}]))
    assert _kod(_kap(tmp_path / 'b.sqlite', meta=m)) in ('bad_imagery_meta', 'bad_imagery_file')
    m2 = _meta()
    m2.update({'ek%d' % i: 'v' for i in range(mpi.MAX_META_ROWS)})
    assert _kod(_kap(tmp_path / 'c.sqlite', meta=m2)) == 'bad_imagery_meta'


def test_karo_icerik_kapilari(tmp_path):
    z, x, y = Z13
    tam = _webp()
    karolar = {
        (13, x, y): (10000, b'RIFF\x00\x00\x00\x00WEBPVP8 ' + b'\x00' * 40),   # RIFF boyu yanlış
        (13, x + 1, y): (10000, _webp(boyut=256)),                            # 256 px
        (13, x + 2, y): (10000, b'\x89PNG\r\n\x1a\n' + b'\x00' * 64),         # WebP değil
        (13, x + 3, y): (10000, tam[:-7]),                                    # kesik
        (13, x + 4, y): (0, tam),                                             # coverage 0
        (13, x + 5, y): (10001, tam),                                         # coverage > 10000
    }
    yol = _kap(tmp_path / 'k.sqlite', karolar)
    ok = mpi.GoruntuOkuyucu(yol)
    try:
        for dx in range(6):
            with pytest.raises(mpi.GoruntuHatasi) as e:
                ok.karo(13, x + dx, y)
            assert e.value.kod == 'bad_tile', dx
    finally:
        ok.kapat()


def test_sisirilmis_karo_tavani(tmp_path):
    z, x, y = Z13
    buyuk = b'RIFF' + struct.pack('<I', mpi.MAX_TILE_BYTES + 100 - 8) + b'WEBP' + \
        b'\x00' * (mpi.MAX_TILE_BYTES + 100 - 12)
    yol = _kap(tmp_path / 'b.sqlite', {(13, x, y): (10000, buyuk)})
    ok = mpi.GoruntuOkuyucu(yol)
    try:
        with pytest.raises(mpi.GoruntuHatasi) as e:
            ok.karo(13, x, y)
        assert e.value.kod in ('tile_too_large', 'bad_imagery_file')
    finally:
        ok.kapat()


def test_sorgu_adim_tavani(gecerli, monkeypatch):
    monkeypatch.setattr(mpi, 'MAX_VM_STEPS', 0)
    with pytest.raises(mpi.GoruntuHatasi) as e:
        mpi.GoruntuOkuyucu(gecerli[0])
    assert e.value.kod == 'imagery_query_limit'


def test_salt_okur_dosya_degismez(gecerli):
    yol = gecerli[0]
    once = hashlib.sha256(open(yol, 'rb').read()).hexdigest()
    ok = mpi.GoruntuOkuyucu(yol)
    try:
        with pytest.raises(sqlite3.Error):
            ok._db.execute("INSERT INTO metadata VALUES ('x','y')")
        for k in _atalar(*Z13):
            ok.karo(*k)
    finally:
        ok.kapat()
    assert hashlib.sha256(open(yol, 'rb').read()).hexdigest() == once


# ---------------------------------------------------------------------------
# 3) WebP başlık çözümü (Pillow'un ürettiği üç biçim)
# ---------------------------------------------------------------------------

def test_webp_boyutu_uc_bicim():
    assert mpi.webp_boyutu(_webp()) == (512, 512)                       # VP8
    assert mpi.webp_boyutu(_webp(kayipsiz=True)) == (512, 512)          # VP8L
    b = _webp(alfa=10)
    assert b[12:16] in (b'VP8X', b'VP8L')
    assert mpi.webp_boyutu(b) == (512, 512)
    assert mpi.webp_boyutu(_webp(boyut=300)) == (300, 300)
    for kotu in (b'', b'RIFF', b'GIF89a' + b'\x00' * 40, None, 'metin'):
        with pytest.raises(mpi.GoruntuHatasi):
            mpi.webp_boyutu(kotu)


# ---------------------------------------------------------------------------
# 4) Zemin sağlayıcı (FS-HARİTA-VERİ F2.4 sözleşmesi)
# ---------------------------------------------------------------------------

def _sha(yol):
    return hashlib.sha256(open(yol, 'rb').read()).hexdigest()


def test_saglayici_tam_kismi_ve_surum(gecerli):
    yol, tam, kismi = gecerli
    z, x, y = Z13
    try:
        fn = mpi.saglayici(lambda: [(yol, _sha(yol))])
        assert re.match(r'^[a-z0-9._-]{1,40}$', fn.surum)
        assert fn(*Z13) == tam
        assert fn(13, x + 1, y) is None                 # kısmi karo varsayılan olarak verilmez
        assert fn(13, x + 9, y) is None                 # kapsam dışı
        assert fn(14, 2 * x, 2 * y) is None             # büyütücü yok
        assert fn(13, -4, 0) is None
        fk = mpi.saglayici(lambda: [(yol, _sha(yol))], kismi_karo=True)
        assert fk(13, x + 1, y) == kismi and fk.surum != fn.surum
        with pytest.raises(mpi.GoruntuHatasi):
            fn('13', 1, 1)
    finally:
        mpi.okuyuculari_birak()


def test_saglayici_buyutucu_atadaki_pencere(gecerli):
    yol, tam, _k = gecerli
    z, x, y = Z13
    alinan = []

    def buyut(ata):
        alinan.append(ata)
        return b'buyutuldu'
    try:
        fn = mpi.saglayici(lambda: [(yol, _sha(yol))], buyutucu=buyut)
        assert fn(14, 2 * x + 1, 2 * y) == b'buyutuldu'
        assert alinan[0].dz == 1 and alinan[0].pencere == (256, 0, 256) and alinan[0].veri == tam
        assert fn(*Z13) == tam                          # düzey içinde büyütücü çağrılmaz
        assert len(alinan) == 1
    finally:
        mpi.okuyuculari_birak()


def test_saglayici_birden_cok_dosya_belirlenimci(tmp_path):
    z, x, y = Z13
    a_kismi = _kap(tmp_path / 'a.sqlite', {(13, x, y): (5000, _webp((200, 0, 0), alfa=256))})
    b_tam = _kap(tmp_path / 'b.sqlite', {(13, x, y): (10000, _webp((0, 200, 0)))},
                 meta=_meta(pack_id='ksc_lc39a'))
    try:
        kay = [(b_tam, _sha(b_tam)), (a_kismi, _sha(a_kismi))]
        fn = mpi.saglayici(lambda: kay)
        ob = mpi.GoruntuOkuyucu(b_tam)
        try:
            assert fn(*Z13) == ob.karo(*Z13)
        finally:
            ob.kapat()
        fk = mpi.saglayici(lambda: list(reversed(kay)), kismi_karo=True)
        assert fk(*Z13) == fn(*Z13)                     # tam karo kısmiden önce, sıra bağımsız
    finally:
        mpi.okuyuculari_birak()


def test_okuyucu_onbellek_dosya_degisince_yeniden_acar(tmp_path):
    z, x, y = Z13
    yol = _kap(tmp_path / 'r.sqlite', {(13, x, y): (10000, _webp((1, 2, 3)))})
    try:
        o1 = mpi.okuyucu(yol, _sha(yol))
        assert mpi.okuyucu(yol, _sha(yol)) is o1
        os.utime(yol, ns=(1, 1))
        o2 = mpi.okuyucu(yol, _sha(yol))
        assert o2 is not o1
        assert o1._db is None                            # eski bağlantı kapandı
    finally:
        mpi.okuyuculari_birak()


def test_okuyucu_onbellek_eszamanli_tek_baglanti(tmp_path):
    import threading
    z, x, y = Z13
    yol = _kap(tmp_path / 'e.sqlite', {(13, x, y): (10000, _webp((9, 9, 9)))})
    h = _sha(yol)
    sonuc, hatalar = [], []

    def is_():
        try:
            o = mpi.okuyucu(yol, h)
            sonuc.append(o)
            assert o.karo(*Z13) is not None
        except Exception as e:          # pragma: no cover - test teşhisi
            hatalar.append(e)
    try:
        ts = [threading.Thread(target=is_) for _ in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert not hatalar and len(set(map(id, sonuc))) == 1
        assert sonuc[0]._db is not None                  # kimse kapatmadı
    finally:
        mpi.okuyuculari_birak()
    assert sonuc[0]._db is None                          # bırakınca kapandı


def test_saglayici_gecersiz_kurulum():
    with pytest.raises(mpi.GoruntuHatasi):
        mpi.saglayici('degil')
    with pytest.raises(mpi.GoruntuHatasi):
        mpi.saglayici(lambda: [], buyutucu=5)


# ---------------------------------------------------------------------------
# 5) Lisans/atıf ve paket sözleşmesiyle tutarlılık
# ---------------------------------------------------------------------------

def test_copernicus_atif_metni(arac):
    # AB Komisyonu "Legal notice on the use of Copernicus Sentinel Data and Service
    # Information" (Delegated Regulation (EU) No 1159/2013 md. 8): değiştirilmiş veri için
    # 'Contains modified Copernicus Sentinel data [Year]'.
    assert mpi.ATTRIBUTION_TEMPLATE == 'Contains modified Copernicus Sentinel data {years}'
    assert arac.atif_metni(['2025', '2024', '2025']) == \
        'Contains modified Copernicus Sentinel data 2024, 2025'


def test_paket_sozlesmesi_sabitleri(arac):
    """FS-HARİTA-VERİ Parça S (map_packs) birleşince sabitler aynı olmalı."""
    assert arac.paket_dosya_adi('sinop_tr') == 'hrma-goruntu-sinop_tr-v2.sqlite'   # şema /2
    assert re.match(r'^[a-z0-9][a-z0-9._-]{0,120}\.(pmtiles|sqlite)$',
                    arac.paket_dosya_adi('ksc_lc39a'))
    with pytest.raises(SystemExit):
        arac.paket_dosya_adi('../x')
    try:
        from hrma.analysis import map_packs
    except ImportError:
        pytest.skip('map_packs (Parça S) bu dalda yok')
    assert mpi.TILE_PX == map_packs.KURE_TILE_PX
    assert mpi.MAX_TILE_BYTES == map_packs.MAX_TILE_BYTES
    assert mpi.MAX_FILE_BYTES == map_packs.MAX_PACK_BYTES
    assert map_packs.COMPONENT_EXT['imagery'] == '.sqlite'
    assert map_packs.PACK_FILE_RE.match(arac.paket_dosya_adi('sinop_tr'))
    assert mpi.READER_MAX_ZOOM == map_packs.PACK_MAX_ZOOM


# ---------------------------------------------------------------------------
# 6) Üretim aracının saf işlevleri (ağ/GDAL yok)
# ---------------------------------------------------------------------------

def test_alan_karolari_hizali_ve_kapsar(arac):
    bbox = (33.943864, 41.124789, 36.362336, 42.921411)          # Parça S sinop_tr kutusu
    k = arac.alan_karolari(bbox)
    w, s, e, n = arac.alan_kutusu(k)
    assert w <= bbox[0] and s <= bbox[1] and e >= bbox[2] and n >= bbox[3]
    sp = tile_cache.tile_span_deg(13)
    assert bbox[0] - w < sp and e - bbox[2] < sp and n - bbox[3] < sp and bbox[1] - s < sp
    for t in (w, e):
        assert abs((t + 180) / sp - round((t + 180) / sp)) < 1e-9


def test_kapsama_degeri_tam_esdeger(arac):
    assert arac.kapsama_degeri(1.0, True, True) == 10000
    assert arac.kapsama_degeri(0.99999999, False, True) == 9999
    assert arac.kapsama_degeri(1e-9, False, True) == 1
    assert arac.kapsama_degeri(0.5, False, True) == 5000


def test_adaylari_sec_ay_yinelenen_ve_k(arac):
    def oz(i, tarih, bulut, mgrs='MGRS-36TXL', dt='A', son=0, nodata=0.0):
        return {'id': 'S2B_%s_%s_%d_L2A' % (mgrs[-5:], tarih.replace('-', ''), son),
                'datetime': tarih + 'T08:00:00Z', 'cloud': bulut, 'nodata': nodata,
                'mgrs': mgrs, 'datatake': dt + str(i)}
    ad = [oz(1, '2025-07-01', 5.0), oz(2, '2025-07-02', 1.0), oz(3, '2025-01-05', 0.0),
          oz(4, '2025-08-01', 2.0, nodata=95.0), oz(5, '2025-07-02', 1.0, son=1, dt='A'),
          oz(6, '2025-09-09', 0.5, mgrs='MGRS-36TWL')]
    ad[4]['datatake'] = ad[1]['datatake']
    sec = arac.adaylari_sec(ad, (6, 7, 8, 9), k=8)
    ids = [s['id'] for s in sec]
    assert 'S2B_36TXL_20250105_0_L2A' not in ids                 # ay dışı
    assert 'S2B_36TXL_20250801_0_L2A' not in ids                 # veri yok %95
    assert 'S2B_36TXL_20250702_1_L2A' in ids and 'S2B_36TXL_20250702_0_L2A' not in ids
    assert len(arac.adaylari_sec(ad, (6, 7, 8, 9), k=1)) == 2    # MGRS başına 1


def test_cog_izin_listesi(arac):
    ok = 'https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/36/T/XL/2025/9/X/TCI.tif'
    assert arac.kabuk_href(ok) == '/vsicurl/' + ok
    for kotu in ('http://sentinel-cogs.s3.us-west-2.amazonaws.com/a/TCI.tif',
                 'https://tiles.maps.eox.at/wmts/a.tif',
                 'https://sentinel-cogs.s3.us-west-2.amazonaws.com.kotu.com/a/TCI.tif',
                 'https://u:p@sentinel-cogs.s3.us-west-2.amazonaws.com/a/TCI.tif',
                 'https://sentinel-cogs.s3.us-west-2.amazonaws.com/a/run.sh'):
        with pytest.raises(SystemExit):
            arac.kabuk_href(kotu)


def test_tiff_karo_baytlari_klasik(arac):
    # 2x2 karo, 16 px karolar, 32x32 görüntü; TileByteCounts = [10, 20, 30, 40]
    girdiler = [(256, 3, 1, 32), (257, 3, 1, 32), (322, 3, 1, 16), (323, 3, 1, 16)]
    veri_ofs = 8 + 2 + 12 * 6 + 4
    girdiler += [(324, 4, 4, veri_ofs), (325, 4, 4, veri_ofs + 16)]
    b = b'II' + struct.pack('<HI', 42, 8) + struct.pack('<H', len(girdiler))
    for tag, tip, say, deger in girdiler:
        b += struct.pack('<HHI', tag, tip, say) + (struct.pack('<HH', deger, 0) if tip == 3
                                                   else struct.pack('<I', deger))
    b += struct.pack('<I', 0) + struct.pack('<4I', 100, 200, 300, 400) + \
        struct.pack('<4I', 10, 20, 30, 40)
    assert arac.tiff_karo_baytlari(b) == (16, 16, 32, 32, [10, 20, 30, 40])
    assert arac.tiff_karo_baytlari(b[:60]) is None                # dizi başlık dışında
    assert arac.tiff_karo_baytlari(b'GIF89a' + b'\x00' * 20) is None


def test_ag_istatistigi_cozumu(arac):
    m = 'satir\nNetwork statistics:\n' + json.dumps(
        {'methods': {'HEAD': {'count': 2}, 'GET': {'count': 5, 'downloaded_bytes': 7142738}}})
    assert arac.ag_istatistigi_coz(m) == 7142738
    assert arac.ag_istatistigi_coz('istatistik yok') == 0


def test_genislet_ve_maske(arac):
    m = np.zeros((9, 9), bool)
    m[4, 4] = True
    g = arac.genislet(m, 2)
    assert g.sum() == 25 and g[2:7, 2:7].all()
    sinif = np.array([[4, 5, 6, 9], [7, 11, 2, 3], [0, 1, 10, 8]], np.uint8)
    iy, kb, gz = arac.maskeler(sinif, 0)
    assert iy.tolist() == [[True, True, True, False], [False, False, False, False],
                           [False, False, False, False]]
    assert kb.tolist() == [[False, False, False, False], [True, True, True, False],
                           [False, False, False, False]]
    assert gz.sum() == 11


def test_acgozlu_plan_belirlenimci_ve_esik(arac):
    H = W = 100
    goz = np.ones((H, W), bool)
    a = np.zeros((H, W), bool)
    a[:, :60] = True
    b = np.zeros((H, W), bool)
    b[:, 50:] = True
    c = np.zeros((H, W), bool)
    c[0, 99] = True                                              # kazanç eşiğin altında
    secim, atama = arac.acgozlu_plan({'A': a, 'B': b, 'C': c}, {}, goz)
    assert [s[0] for s in secim] == ['A', 'B']
    assert secim[0][2] == 6000 and secim[1][2] == 4000
    assert (atama[:, :60] == 0).all() and (atama[:, 60:] == 1).all()
    secim2, atama2 = arac.acgozlu_plan({'B': b, 'A': a, 'C': c}, {}, goz)
    assert secim2 == secim and (atama2 == atama).all()


def test_renk_uydur_ortalama_sapma(arac):
    rng = np.random.default_rng(7)
    x = rng.uniform(20, 200, size=(3, 4000)).astype(np.float32)
    y = 1.1 * x + 5.0
    y[:, :100] = 255.0                                           # değişmiş pikseller (aykırı)
    m = np.ones(4000, bool)
    r = arac.renk_uydur(y, x, m)
    for a, b, n, tur in r:
        assert tur == 'uyduruldu' and abs(a - 1.1) < 0.01 and abs(b - 5.0) < 1.0
    r2 = arac.renk_uydur(y, x, np.zeros(4000, bool))
    assert all(t[3] == 'birim' and t[0] == 1.0 for t in r2)


def test_renk_dengesi_yalniz_kara_pikselleri(arac):
    """İkinci edinim karada referansın 1,2 katı, denizde bambaşka renk: kazanç kara verisinden."""
    H = W = 60
    rng = np.random.default_rng(3)
    kara = np.zeros((H, W), bool)
    kara[:, :30] = True
    sinif_a = np.where(kara, 4, 6).astype(np.uint8)
    sinif_b = sinif_a.copy()
    taban = rng.uniform(40, 160, size=(3, H, W)).astype(np.float32)
    tci_a = taban.copy()
    tci_b = taban / 1.2
    tci_b[:, ~kara] = 200.0                                      # deniz: plankton/yansıma
    edinim = {'A': ['a'], 'B': ['b']}
    r = arac.renk_dengesi(['A', 'B'], edinim, {'a': sinif_a, 'b': sinif_b},
                          {'a': tci_a, 'b': tci_b}, H, W)
    assert r['A'][0][3] == 'referans'
    for a, b, n, tur in r['B']:
        assert tur == 'uyduruldu' and abs(a - 1.2) < 0.02 and abs(b) < 2.0
    r2 = arac.renk_dengesi(['A', 'B'], edinim, {'a': sinif_a, 'b': sinif_b},
                           {'a': tci_a, 'b': tci_b}, H, W)
    assert r2 == r                                               # belirlenimci


def test_acgozlu_plan_kabul_gecisi(arac):
    goz = np.ones((10, 10), bool)
    iyi = {'A': np.zeros((10, 10), bool)}
    iyi['A'][:, :8] = True
    kabul = {'K': np.zeros((10, 10), bool)}
    kabul['K'][:, 8:] = True
    secim, atama = arac.acgozlu_plan(iyi, kabul, goz)
    assert [(s[0], s[1]) for s in secim] == [('A', 'iyi'), ('K', 'kabul')]
    assert (atama >= 0).all()


def test_kalici_parlak_su_istisnasi(arac):
    """Tuz gölü (her edinimde SCL 6 + parlak) kalıcı; tek tarihte parlak su (bulut) kalıcı değil."""
    H, W = 4, 6
    scl, tci, ed = {}, {}, {}
    for i, e in enumerate(('E1', 'E2', 'E3')):
        g = 'G%d' % i
        scl[g] = np.full((H, W), 6, np.uint8)
        t = np.full((3, H, W), 30, np.uint8)          # koyu su
        t[:, :, 0] = 220                               # sütun 0: her tarihte parlak (tuz gölü)
        if i == 0:
            t[:, :, 1] = 220                           # sütun 1: yalnız bir tarihte parlak (bulut)
        if i < 2:
            t[:, :, 2] = 220                           # sütun 2: 2/3 tarihte parlak (oran 0,67)
        tci[g], ed[g] = t, e
    # Aynı edinimin komşu granülü sayımı İKİLEMEZ
    scl['G0b'], tci['G0b'], ed['G0b'] = scl['G0'].copy(), tci['G0'].copy(), 'E1'
    k = arac.kalici_parlak_su(scl, tci, ed, H, W)
    assert k[:, 0].all() and not k[:, 1].any() and k[:, 2].all() and not k[:, 3:].any()
    tek = arac.kalici_parlak_su({'G0': scl['G0'], 'G0b': scl['G0b']},
                                {'G0': tci['G0'], 'G0b': tci['G0b']}, ed, H, W)
    assert not tek.any()                                 # tek edinim (iki granül) kalıcı sayılmaz
    assert arac.KALICI_PARLAK_SU_EN_AZ == 2 and arac.KALICI_PARLAK_SU_ORAN == 0.5


def test_kaba_pencere_eslemesi(arac):
    """z13 penceresi -> kaba hücre (32 z13 px) eşlemesi; ızgara dışı False."""
    plan = {'alan_karolari_z13': [8 * 100, 8 * 50, 8 * 100 + 16, 8 * 50 + 16]}   # blok (100, 50)
    K = mpi.TILE_PX // arac.KABA_BOLUM
    kal = np.zeros((16 * arac.KABA_BOLUM, 16 * arac.KABA_BOLUM), bool)
    kal[1, 2] = True
    p = arac._kaba_pencere(kal, plan, 100, 50, 0, 0, 4 * K, 4 * K)
    assert p[K:2 * K, 2 * K:3 * K].all() and int(p.sum()) == K * K
    disari = arac._kaba_pencere(kal, plan, 100, 50, -3 * K, -3 * K, 2 * K, 2 * K)
    assert not disari.any()
    assert not arac._kaba_pencere(None, plan, 100, 50, 0, 0, 8, 8).any()


def test_arac_hrma_paketini_bozmaz(arac):
    """Araç tam ortamda gerçek ``hrma.analysis`` paketini kullanır (sahte paket sokmaz)."""
    import sys
    assert hasattr(sys.modules['hrma.analysis'], '__file__')
    assert arac.mpi is mpi and arac.tile_cache is tile_cache


# ---------------------------------------------------------------------------
# 7) Üretilmiş pilot paketi (yerelde varsa; git dışı kalıcı dizin)
# ---------------------------------------------------------------------------
PAKET_DIZINI = os.path.expanduser('~/HRMA-calisma/2026-11-18/GORUNTU-HAFIF/paketler')


@pytest.mark.parametrize('saha', ['sinop_tr', 'ccsfs_slc40'])
def test_uretilmis_pilot_paketi(saha):
    yol = os.path.join(PAKET_DIZINI, 'hrma-goruntu-%s-v2.sqlite' % saha)
    if not os.path.exists(yol):
        pytest.skip('pilot paketi bu makinede yok')
    ok = mpi.GoruntuOkuyucu(yol)
    try:
        b = ok.bilgi
        assert b['pack_id'] == saha and (b['zoom_min'], b['zoom_max']) == (9, 13)
        assert b['attribution'].startswith('Contains modified Copernicus Sentinel data 20')
        assert b['license'] == mpi.LICENSE_ID
        assert all(re.match(r'^S2[ABC]_[0-9A-Z]{5}_\d{8}_\d+_L2A$', s['id']) for s in b['scenes'])
        w, s, e, n = b['bounds']
        lon, lat = (w + e) / 2, (s + n) / 2
        for z in range(9, 14):
            x, y = tile_cache.lonlat_to_tile(z, lon, lat)
            r = ok.karo_bilgisi(z, x, y)
            if r is not None:
                assert mpi.webp_boyutu(ok.karo(z, x, y)) == (512, 512)
    finally:
        ok.kapat()


# ===========================================================================
# 8) 17 Kas — okuyucunun haritaya bağlanması (map_packs.goruntu_zemini_kaydet),
#    paket listesi bileşeni, lisans bildirimi, panel ve harita üstü atıf
# ===========================================================================
import shutil  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402

from hrma.analysis import map_packs as MP  # noqa: E402
from tests.test_v307_harita_paket import GX, GY, GZ, LAT, LON, _ornek_karolar  # noqa: E402

NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node bulunamadı')
PANEL_JS = os.path.join(DEPO, 'hrma', 'static', 'js', 'launch_site_map_packs.js')
I18N_JS = os.path.join(DEPO, 'hrma', 'static', 'js', 'i18n_launch_site.js')
GERCEK_LISTE = os.path.join(DEPO, 'hrma', 'static', 'map', 'harita_paketleri.json')
ATIF_RE = re.compile(r'^Contains modified Copernicus Sentinel data 20\d\d(, 20\d\d)*$')
SAHNE_RE = re.compile(r'^S2[ABC]_[0-9A-Z]{5}_\d{8}_\d+_L2A$')
GORUNTU_RENK = (40, 90, 60)
KISMI_RENK = (10, 20, 200)
#: Görüntü kapsamı dışında ama vektör paketinin içinde kalan karo (3 karo doğuda).
DIS_X = GX + 3


def _goruntu_kabi(yol):
    """GZ/GX/GY karosu (tam) + dört z13 çocuğu (biri kısmi, üst 100 satır saydam)."""
    karolar = {(GZ, GX, GY): (10000, _webp(GORUNTU_RENK))}
    for dx in (0, 1):
        for dy in (0, 1):
            karolar[(GZ + 1, 2 * GX + dx, 2 * GY + dy)] = (10000, _webp(GORUNTU_RENK))
    karolar[(GZ + 1, 2 * GX + 1, 2 * GY)] = (8047, _webp(KISMI_RENK, alfa=100))
    sinir = tile_cache.tile_to_bbox(GZ, GX, GY)
    meta = _meta(zoom_min=str(GZ), zoom_max=str(GZ + 1), pack_id='sinop_test',
                 bounds=','.join('%.9f' % v for v in sinir))
    return _kap(yol, karolar, meta)


@pytest.fixture
def kurulum(tmp_path, monkeypatch):
    """Yalıtılmış kurulum dizini + liste (vektör + görüntü bileşeni) + karo önbelleği."""
    maps = tmp_path / 'maps'
    maps.mkdir()
    monkeypatch.setattr(MP, '_KURULUM_DIZINI_SAGLAYICI', lambda: str(maps))
    monkeypatch.setenv('HRMA_TILE_CACHE_DIR', str(tmp_path / 'tiles'))
    karolar, _vz = _ornek_karolar()
    vek = tmp_path / 'kaynak.pmtiles'
    bbox = MP.daire_bbox(LAT, LON, 30.0)
    MP.pmtiles_yaz(str(vek), karolar, {'name': 'test'}, bbox)
    gor = tmp_path / 'kaynak.sqlite'
    _goruntu_kabi(str(gor))
    vveri, gveri = vek.read_bytes(), gor.read_bytes()
    bil = [{'kind': 'vector', 'file': 'hrma-harita-sinop_test-v1.pmtiles', 'size_bytes': len(vveri),
            'sha256': hashlib.sha256(vveri).hexdigest(), 'license': 'ODbL-1.0',
            'attribution': '(c) OpenStreetMap contributors'},
           {'kind': 'imagery', 'file': 'hrma-goruntu-sinop_test-v1.sqlite', 'size_bytes': len(gveri),
            'sha256': hashlib.sha256(gveri).hexdigest(), 'license': mpi.LICENSE_ID,
            'attribution': mpi.ATTRIBUTION_TEMPLATE.format(years='2025'),
            'detail': {'full_zoom_max': mpi.IMAGERY_FULL_ZOOM_MAX,
                       'rings': [{'zoom': z, 'radius_km': r} for z, r in mpi.IMAGERY_RINGS]}}]
    m = {'schema': MP.MANIFEST_SCHEMA, 'release_tag': 'harita-paketleri-test',
         'packs': [{'id': 'sinop_test', 'kind': 'site', 'name_key': 'site.mapPackName.sinop_test',
                    'bbox': [round(v, 6) for v in bbox], 'zoom_max': 15, 'components': bil}]}
    man = tmp_path / 'harita_paketleri.json'
    man.write_text(json.dumps(m), encoding='utf-8')
    monkeypatch.setattr(MP, 'MANIFEST_PATH', str(man))
    for c in (MP._manifest_cache, MP._durumlar, MP._dogrulama_cache):
        c.clear()
    for yol in list(MP._okuyucular):
        MP._okuyucu_birak(yol)
    mpi.okuyuculari_birak()
    monkeypatch.setattr(MP, '_ZEMIN_SAGLAYICI', None)

    def kur(vektor=True, goruntu=True, goruntu_bayt=None):
        if vektor:
            (maps / bil[0]['file']).write_bytes(vveri)
        if goruntu:
            (maps / bil[1]['file']).write_bytes(gveri if goruntu_bayt is None else goruntu_bayt)
    yield {'maps': maps, 'kur': kur, 'manifest': m, 'man': man, 'gveri': gveri, 'bil': bil}
    for yol in list(MP._okuyucular):
        MP._okuyucu_birak(yol)
    mpi.okuyuculari_birak()
    for c in (MP._manifest_cache, MP._durumlar, MP._dogrulama_cache):
        c.clear()


def _rgba(b):
    with Image.open(io.BytesIO(b)) as im:
        return np.asarray(im.convert('RGBA'))


def test_kanca_goruntu_kurulu_degilken_bit_ayni(kurulum):
    kurulum['kur'](goruntu=False)
    yalin = {(z, x): MP.karo_ciz(z, x, GY if z == GZ else 2 * GY) for z, x in
             ((GZ, GX), (GZ, DIS_X), (GZ + 1, 2 * GX))}
    anahtar = MP.onbellek_anahtari(GZ, GX, GY)
    MP.goruntu_zemini_kaydet()
    assert MP.zemin_kimligi() == 'img2-k1-b1'
    assert MP.kurulu_goruntu_kaynaklari() == []
    for (z, x), b in yalin.items():
        assert MP.karo_ciz(z, x, GY if z == GZ else 2 * GY) == b, (z, x)   # BİT-AYNI
    assert MP.onbellek_anahtari(GZ, GX, GY) != anahtar          # sağlayıcı sürümü anahtarda


def test_kanca_tam_karo_goruntu_zemini_opak(kurulum):
    kurulum['kur']()
    yalin_dis = MP.karo_ciz(GZ, DIS_X, GY)
    yalin = MP.karo_ciz(GZ, GX, GY)
    anahtar = MP.onbellek_anahtari(GZ, GX, GY)
    MP.goruntu_zemini_kaydet()
    assert [os.path.basename(y) for y, _s in MP.kurulu_goruntu_kaynaklari()] == \
        ['hrma-goruntu-sinop_test-v1.sqlite']
    b = MP.karo_ciz(GZ, GX, GY)
    assert b != yalin and b[12:16] == b'VP8 '                   # opak, kayıplı
    a = _rgba(b)
    assert a[..., 3].min() == 255
    renk, sayi = np.unique(a[..., :3].reshape(-1, 3), axis=0, return_counts=True)
    baskin = renk[np.argmax(sayi)]
    assert np.all(np.abs(baskin.astype(int) - GORUNTU_RENK) <= 6), baskin
    # Görüntü kapsamı dışındaki karo: sağlayıcı None -> vektör yolu bit-aynı
    assert MP.karo_ciz(GZ, DIS_X, GY) == yalin_dis
    # Görüntü bileşeninin özeti anahtara girer (bileşen değişince eski karo sunulmaz)
    assert MP.onbellek_anahtari(GZ, GX, GY) != anahtar


def test_kanca_kismi_karo_alfa_korunur_sahte_dolgu_yok(kurulum):
    kurulum['kur']()
    MP.goruntu_zemini_kaydet()
    b = MP.karo_ciz(GZ + 1, 2 * GX + 1, 2 * GY)
    assert b[12:16] == b'VP8X'                                  # alfalı WebP
    a = _rgba(b)
    assert a[:90, :, 3].max() == 0                              # veri yok: SAYDAM (siyah değil)
    assert a[110:, :, 3].min() == 255
    assert np.all(np.abs(np.median(a[110:, :, :3].reshape(-1, 3), axis=0) - KISMI_RENK) <= 8)
    # Karo ucu yolu: alfalı WebP önbelleğe girer ve geçerli sayılır (ikinci istek önbellekten)
    r1 = tile_cache.resolve_tile('pack_detail', GZ + 1, 2 * GX + 1, 2 * GY)
    r2 = tile_cache.resolve_tile('pack_detail', GZ + 1, 2 * GX + 1, 2 * GY)
    assert r1['ok'] and r1['cached'] is False and r2['ok'] and r2['cached'] is True
    assert open(r2['path'], 'rb').read() == b


def test_kanca_z14_z15_atadan_buyutme(kurulum):
    kurulum['kur']()
    MP.goruntu_zemini_kaydet()
    for z in (GZ + 2, GZ + 3):
        k = 1 << (z - GZ - 1)
        b = MP._ZEMIN_SAGLAYICI(z, 2 * GX * k, 2 * GY * k + k)   # tam z13 atası
        assert b[:8] == b'\x89PNG\r\n\x1a\n'                     # ara adımda kayıpsız
        with Image.open(io.BytesIO(b)) as im:
            assert im.size == (512, 512) and im.mode == 'RGB'
        t = MP.karo_ciz(z, 2 * GX * k, 2 * GY * k + k)
        assert _rgba(t)[..., 3].min() == 255
    # Kısmi atanın penceresi alfalı büyütülür (öncarpımlı)
    b = MP._ZEMIN_SAGLAYICI(GZ + 2, 2 * (2 * GX + 1), 2 * (2 * GY))
    with Image.open(io.BytesIO(b)) as im:
        assert im.mode == 'RGBA' and im.getchannel('A').getextrema() == (0, 255)
    assert MP._ZEMIN_SAGLAYICI(GZ + 4, 0, 0) is None             # tavan üstü (> 2 düzey) yok


def test_zemin_varken_alan_dolgulari_cizilmez():
    from PIL import ImageDraw
    L = {'water': {'extent': 4096, 'features': [(3, {'kind': 'water'},
                                                [[(0, 0), (4096, 0), (4096, 4096), (0, 4096), (0, 0)]])]},
         'landuse': {'extent': 4096, 'features': [(3, {'kind': 'wood'},
                                                  [[(0, 0), (4096, 0), (4096, 4096), (0, 4096)]])]}}
    sonuc = {}
    for zv in (False, True):
        im = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
        d = ImageDraw.Draw(im, 'RGBA')
        w, s, e, n = MP.merc_lonlat(10, 600, 380)[0], 0, 0, MP.merc_lonlat(10, 600, 380)[1]
        e, s = MP.merc_lonlat(10, 601, 381)
        MP._mvt_ciz(d, L, 10, 600, 380, w, n, 256 / (e - w), 256 / (n - s), 0, 0, 12, zemin_var=zv)
        sonuc[zv] = np.asarray(im)
    assert sonuc[False][128, 128, 3] > 0                         # zeminsiz: dolgu var (bugünkü)
    assert sonuc[True][128, 128, 3] == 0                         # zeminli: iç saydam
    assert sonuc[True][..., 3].max() > 0                         # kıyı çizgisi kalır


def test_bozuk_goruntu_bileseni_adli_503(kurulum):
    bozuk = b'SQLite format 3\x00' + b'\x00' * 4000
    m = kurulum['manifest']
    m['packs'][0]['components'][1].update(size_bytes=len(bozuk),
                                          sha256=hashlib.sha256(bozuk).hexdigest())
    kurulum['man'].write_text(json.dumps(m), encoding='utf-8')
    MP._manifest_cache.clear()
    kurulum['kur'](goruntu_bayt=bozuk)
    MP.goruntu_zemini_kaydet()
    with pytest.raises(MP.PaketHatasi) as e:
        MP.karo_ciz(GZ, GX, GY)
    assert e.value.kod == 'bad_imagery_file'
    r = tile_cache.resolve_tile('pack_detail', GZ, GX, GY)
    assert r['code'] == 503 and r['error_code'] == 'bad_imagery_file'


def test_sisirilmis_ya_da_degistirilmis_goruntu_okunmaz(kurulum):
    kurulum['kur'](goruntu_bayt=kurulum['gveri'] + b'\x00' * 10)   # boyut/sha tutmuyor
    MP.goruntu_zemini_kaydet()
    assert MP.kurulu_goruntu_kaynaklari() == []
    assert MP.karo_ciz(GZ, GX, GY)[12:16] != b'VP8 '             # görüntüsüz (saydam vektör)


def test_inmekte_olan_paketin_goruntusu_okunmaz(kurulum):
    kurulum['kur']()
    MP._durum_yaz('sinop_test', state='downloading', bytes_done=1, bytes_total=2)
    assert MP.kurulu_goruntu_kaynaklari() == []


def test_ozet_bilesenler_boyut_ve_kurulum(kurulum):
    kurulum['kur'](goruntu=False)
    p = MP.paketler_ozeti()[0]
    bil = {c['kind']: c for c in p['components']}
    assert set(bil) == {'vector', 'imagery'}
    assert p['size_bytes'] == sum(b['size_bytes'] for b in kurulum['bil'])
    assert bil['imagery']['installed'] is False and bil['vector']['installed'] is True
    assert p['status'] == 'not_installed'                       # bütün bileşenler kurulu değil
    assert p['license'] == 'ODbL-1.0; ' + mpi.LICENSE_ID
    assert bil['imagery']['attribution'] == mpi.ATTRIBUTION_TEMPLATE.format(years='2025')
    # Halka kuralı panel için: yarıçaplar listeden, piksel boyları koddan (piksel_metre)
    assert bil['imagery']['detail'] == {
        'full_zoom_max': 11, 'full_m_per_px': 30.6,
        'rings': [{'zoom': 12, 'radius_km': 50.0, 'm_per_px': 15.3},
                  {'zoom': 13, 'radius_km': 25.0, 'm_per_px': 7.6}]}
    assert 'detail' not in bil['vector']
    kurulum['kur']()
    p = MP.paketler_ozeti()[0]
    assert p['status'] == 'installed' and all(c['installed'] for c in p['components'])


def test_paket_sil_goruntu_baglantisini_kapatir(kurulum):
    kurulum['kur']()
    MP.goruntu_zemini_kaydet()
    MP.karo_ciz(GZ, GX, GY)
    yol = os.path.realpath(str(kurulum['maps'] / 'hrma-goruntu-sinop_test-v1.sqlite'))
    assert yol in mpi._okuyucular
    MP.paket_sil('sinop_test')
    assert yol not in mpi._okuyucular and not os.path.exists(yol)
    assert MP.kurulu_goruntu_kaynaklari() == []


def test_eszamanli_cizim_ayni_bayt(kurulum):
    kurulum['kur']()
    MP.goruntu_zemini_kaydet()
    isler = [(GZ, GX, GY), (GZ + 1, 2 * GX, 2 * GY), (GZ + 1, 2 * GX + 1, 2 * GY),
             (GZ + 2, 4 * GX, 4 * GY)]
    seri = {k: MP.karo_ciz(*k) for k in isler}
    sonuc, hata = [], []

    def isci():
        try:
            for _ in range(3):
                for k in isler:
                    sonuc.append((k, MP.karo_ciz(*k)))
        except Exception as e:                                   # pragma: no cover
            hata.append(e)
    th = [threading.Thread(target=isci) for _ in range(8)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    assert not hata and len(sonuc) == 8 * 3 * len(isler)
    assert all(b == seri[k] for k, b in sonuc)                  # belirlenimci
    assert len([y for y in mpi._okuyucular]) == 1                # tek bağlantı


def _cagrilar(ad):
    """hrma/ altındaki gerçek ÇAĞRI düğümleri (yorum/belge dizesi sayılmaz; ast)."""
    import ast
    out = []
    for kok, _d, dosyalar in os.walk(os.path.join(DEPO, 'hrma')):
        for f in dosyalar:
            if not f.endswith('.py'):
                continue
            agac = ast.parse(open(os.path.join(kok, f), encoding='utf-8').read())
            for n in ast.walk(agac):
                if isinstance(n, ast.Call):
                    h = n.func
                    if (isinstance(h, ast.Attribute) and h.attr == ad) or \
                            (isinstance(h, ast.Name) and h.id == ad):
                        out.append(f)
    return out


def test_uygulama_acilisinda_tek_acik_kayit(monkeypatch):
    import hrma.app as uyg
    assert _cagrilar('goruntu_zemini_kaydet') == ['app.py']           # tek yer
    assert _cagrilar('_harita_goruntu_zeminini_bagla') == ['app.py']  # modül düzeyinde bir kez
    # İthal yan etkisi yok: okuyucu modülü sağlayıcıyı kendisi kaydetmez.
    assert 'map_pack_imagery.py' not in _cagrilar('zemin_saglayici_kaydet')
    monkeypatch.setattr(MP, '_ZEMIN_SAGLAYICI', None)
    uyg._harita_goruntu_zeminini_bagla()
    assert MP.zemin_kimligi() == 'img2-k1-b1'


def test_depodaki_liste_goruntu_bilesenleri():
    m = json.load(open(GERCEK_LISTE, encoding='utf-8'))
    MP.manifest_dogrula(m)
    goruntulu = 0
    for p in m['packs']:
        g = [b for b in p['components'] if b['kind'] == 'imagery']
        if p['kind'] == 'region':
            assert not g, p['id']                                # bölge paketinde görüntü yok
            continue
        if not g:
            continue
        goruntulu += 1
        b = g[0]
        assert b['file'] == 'hrma-goruntu-%s-v2.sqlite' % p['id']
        assert MP.goruntu_ayrinti_ozeti(b['detail'])['rings'][-1]['zoom'] == mpi.IMAGERY_ZOOM_MAX
        assert b['license'] == mpi.LICENSE_ID and ATIF_RE.match(b['attribution']), b
        src = b['source']
        assert src['scenes'] and all(SAHNE_RE.match(s) for s in src['scenes'])
        assert src['acquisition_dates'] == sorted(set(src['acquisition_dates']))
        yillar = sorted(set(d[:4] for d in src['acquisition_dates']))
        assert b['attribution'] == mpi.ATTRIBUTION_TEMPLATE.format(years=', '.join(yillar))
        assert (src['zoom_min'], src['zoom_max']) == (mpi.IMAGERY_ZOOM_MIN, mpi.IMAGERY_ZOOM_MAX)
        yol = os.path.join(PAKET_DIZINI, b['file'])
        if os.path.exists(yol):                                  # üretim makinesinde: dosyayla aynı
            assert os.path.getsize(yol) == b['size_bytes']
            assert _sha(yol) == b['sha256'], p['id']
            ok = mpi.GoruntuOkuyucu(yol)
            try:
                assert ok.bilgi['pack_id'] == p['id'] and ok.bilgi['attribution'] == b['attribution']
                assert sorted(s['id'] for s in ok.bilgi['scenes']) == src['scenes']
            finally:
                ok.kapat()
    assert goruntulu >= 4


def test_lisans_bildirimi_copernicus():
    metin = open(os.path.join(DEPO, 'packaging', 'licenses', 'THIRD_PARTY_NOTICES.txt'),
                 encoding='utf-8').read()
    bolum = [b for b in re.split(r'^== ', metin, flags=re.M)
             if re.search(r'^Data:\s*hrma/static/map/harita_paketleri\.json\s*$', b, flags=re.M)]
    assert len(bolum) == 1
    b = bolum[0]
    assert re.search(r'^Pack-Licence:\s*%s\s*$' % re.escape(mpi.LICENSE_ID), b, flags=re.M)
    assert 'Contains modified Copernicus Sentinel data <years>' in b
    assert 'https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice' in b
    assert 'no synthetic fill' in b


def _sozluk():
    kod = r"""
    const fs = require('fs'), vm = require('vm'); let d = null;
    const ctx = { window: {} }; ctx.window.I18N = { register: x => { d = x; } };
    vm.createContext(ctx); vm.runInContext('var window = this.window;' + fs.readFileSync(process.env.SOZLUK_YOLU, 'utf8'), ctx);
    process.stdout.write(JSON.stringify(d));
    """
    r = subprocess.run([NODE], input=kod, capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, SOZLUK_YOLU=I18N_JS))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@node_gerek
def test_i18n_goruntu_anahtarlari_en_tr():
    d = _sozluk()
    for k, yer in (('site.mapPackImagery', ('{size}', '{notice}')),
                   ('site.mapPackImageryDetail', ('{r1}', '{r2}', '{m2}', '{m3}')),
                   ('site.mapPackConsentImagery', ('{size}', '{notice}')),
                   ('site.mapPackImageryAttribution', ('{notice}',))):
        for dil in ('en', 'tr'):
            v = d[dil][k]
            assert all(y in v for y in yer), (dil, k)
            assert '/api/' not in v and 'HTTP' not in v and 'uydur' not in v.lower()
        assert d['en'][k] != d['tr'][k]
    for dil in ('en', 'tr'):                                     # yardım metni iki dosyayı söyler
        assert 'Sentinel-2' in d[dil]['site.help.mapPacks'] and 'Sentinel-2' in d[dil]['site.mapPacksHint']


PANEL_GORUNTU_DUZENEK = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
class Dugum {
    constructor(ad) { this.ad = ad; this.children = []; this.attr = {}; this.style = {}; this._t = '';
                      this.dinle = {}; this.parentNode = null; this.id = ''; }
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
    insertBefore(c, ref) { c.parentNode = this; const i = ref ? this.children.indexOf(ref) : -1;
                           if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); return c; }
    removeChild(c) { this.children = this.children.filter(x => x !== c); }
    get firstChild() { return this.children[0] || null; }
    get nextSibling() { const p = this.parentNode; if (!p) return null;
                        const i = p.children.indexOf(this); return p.children[i + 1] || null; }
    setAttribute(k, v) { this.attr[k] = String(v); }
    getAttribute(k) { return this.attr[k] === undefined ? null : this.attr[k]; }
    addEventListener(t, f) { (this.dinle[t] = this.dinle[t] || []).push(f); }
    set textContent(v) { this._t = String(v); this.children = []; }
    get textContent() { return this._t + this.children.map(c => c.textContent).join(''); }
    tumu() { return [this].concat(...this.children.map(c => c.tumu())); }
}
const notlar = new Dugum('div'), kunye = new Dugum('div');
const kok = { liste: new Dugum('div'), ozet: new Dugum('div'), kunye: kunye, notlar: notlar };
const doc = { createElement: a => new Dugum(a), getElementById: id => kok[id] || null };
const DURUM = JSON.parse(process.env.DURUM);
const KUTU = [34.8, 41.9, 35.4, 42.2];
function paket(gKurulu) {
    return { id: 'sinop_tr', kind: 'site', name_key: 'site.mapPackName.sinop_tr', bbox: [33.94, 41.12, 36.36, 42.92],
             zoom_max: 15, size_bytes: 130695826, sha256: 'ab', license: 'ODbL-1.0; Copernicus-Sentinel-Data-Legal-Notice',
             status: DURUM.status, progress: null, error_code: null,
             components: [{ kind: 'vector', size_bytes: 34513554, sha256: 'ab', license: 'ODbL-1.0',
                            attribution: '(c) OSM', installed: true },
                          { kind: 'imagery', size_bytes: 96182272, sha256: 'cd', license: 'Copernicus-Sentinel-Data-Legal-Notice',
                            attribution: 'Contains modified Copernicus Sentinel data 2024, 2025', installed: gKurulu,
                            detail: DURUM.detail === undefined
                                ? { full_zoom_max: 11, full_m_per_px: 30.6,
                                    rings: [{ zoom: 12, radius_km: 50, m_per_px: 15.3 }, { zoom: 13, radius_km: 25, m_per_px: 7.6 }] }
                                : DURUM.detail }] };
}
const fetchImpl = url => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({ packs: [paket(DURUM.gKurulu)] }) });
let kunyeFn = null;
const ctx = { console, Math, JSON, Promise, setTimeout, encodeURIComponent, String, Number, Array,
              setInterval: f => { kunyeFn = f; return 1; }, clearInterval: () => {} };
ctx.window = ctx;
ctx.I18N = { t: k => k, has: () => true, number: (v, n) => Number(v).toFixed(n),
             tf: (k, p) => k + ' ' + JSON.stringify(p), onChange: () => {}, applyTo: () => {} };
ctx.launchGlobe = { getTileInfo: () => ({ pack: { active: DURUM.aktif, attributionKey: 'site.mapPackAttribution' } }),
                    getTrackingContext: () => ({ camera: {}, globeRadius: 1 }) };
ctx.LaunchSiteLabels = { gorunenKutu: () => (DURUM.kutu === null ? null : { kutu: DURUM.kutu || KUTU }) };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.env.PANEL_YOLU, 'utf8'), ctx);
const P = ctx.LaunchSiteMapPacks;
(async () => {
    await P.bind({ liste: 'liste', ozet: 'ozet', kunye: 'kunye', notlar: 'notlar', fetchImpl, document: doc });
    const satir = kok.liste.textContent;
    const ind = kok.liste.tumu().find(d => d.attr['data-paket-eylem'] === 'indir');
    if (ind) ind.dinle.click.forEach(f => f());
    const onay = kok.liste.textContent;
    kunyeFn();
    const g = notlar.children.find(d => d.attr['data-paket-kunye'] === 'goruntu');
    process.stdout.write(JSON.stringify({ satir, onay, goruntuDugumu: !!g, gk: P.goruntuluKutular(),
        sira: notlar.children.map(d => d.id || d.attr['data-paket-kunye'] || 'osm'),
        gorunur: g ? g.style.display !== 'none' : null, metin: g ? g.textContent : null }));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


def _panel(durum):
    r = subprocess.run([NODE], input=PANEL_GORUNTU_DUZENEK, capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, PANEL_YOLU=PANEL_JS, DURUM=json.dumps(durum)))
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout)


@node_gerek
def test_panel_goruntu_satiri_ve_onay_metni():
    o = _panel({'status': 'not_installed', 'gKurulu': False, 'aktif': False})
    # Satır: OSM lisans cümlesi vektör lisansıyla (görüntü kimliği oraya girmez) + görüntü satırı
    assert 'site.mapPackLicence {"licence":"ODbL-1.0"}' in o['satir']
    assert 'site.mapPackImagery {"size":"96.2 MB","notice":"Contains modified Copernicus Sentinel data 2024, 2025"}' \
        in o['satir']
    assert 'site.mapPackName.sinop_tr130.7 MB' in o['satir']      # toplam boyut indirmeden önce
    # Onay: OSM cümlesi + görüntü cümlesi (boyut ve bildirimle)
    assert 'site.mapPackConsent {' in o['onay'] and '"licence":"ODbL-1.0"' in o['onay']
    assert 'site.mapPackConsentImagery {"size":"96.2 MB"' in o['onay']
    # Halka kuralı cümlesi: yarıçaplar ve piksel boyları sunucu özetinden (satır + onay)
    hc = 'site.mapPackImageryDetail {"r1":"25","r2":"50","m2":"15","m3":"31"}'
    assert hc in o['satir'] and hc in o['onay']
    # Kural iki halka biçiminde değilse cümle YOK (uydurma metin yok)
    o2 = _panel({'status': 'not_installed', 'gKurulu': False, 'aktif': False,
                 'detail': {'full_zoom_max': 13, 'full_m_per_px': 7.6, 'rings': []}})
    assert 'mapPackImageryDetail' not in o2['satir'] and 'site.mapPackImagery {' in o2['satir']


@node_gerek
@pytest.mark.parametrize('durum,gorunur', [
    ({'status': 'installed', 'gKurulu': True, 'aktif': True}, True),
    ({'status': 'installed', 'gKurulu': True, 'aktif': True, 'kutu': None}, True),      # alan ölçülemedi
    ({'status': 'installed', 'gKurulu': True, 'aktif': True, 'kutu': [10, 10, 11, 11]}, False),
    ({'status': 'installed', 'gKurulu': True, 'aktif': False}, False),
    ({'status': 'not_installed', 'gKurulu': False, 'aktif': True}, False),
])
def test_harita_ustu_goruntu_bildirimi(durum, gorunur):
    o = _panel(durum)
    assert o['goruntuDugumu'] is True
    assert o['sira'][:2] == ['osm', 'ls-pack-img-attr']        # OSM künyesinin hemen ardında
    assert o['gorunur'] is gorunur, o
    # Küre için: görüntüsü KURULU paketlerin kutuları (DEVİR: taban doku notları)
    assert o['gk'] == ([{'id': 'sinop_tr', 'bbox': [33.94, 41.12, 36.36, 42.92]}]
                       if durum['status'] == 'installed' and durum['gKurulu'] else [])
    if gorunur:
        assert o['metin'] == ('site.mapPackImageryAttribution {"notice":"Contains modified '
                              'Copernicus Sentinel data 2024, 2025"}')


# ===========================================================================
# 9) 18 Kas — GÖRÜNTÜ-HAFİF: halka kuralı (z13 yalnız rampanın 25 km çevresi, z12 50 km,
#    z9-z11 paket kutusu); halka dışında okuyucu atayı büyütür (boşluksuz geçiş)
# ===========================================================================
HLAT, HLON = 42.0231, 35.1531                      # Sinop ön ayarı (paket merkezi)


def _hkutu():
    return MP.daire_bbox(HLAT, HLON, MP.SITE_RADIUS_KM)


def _dogu(km):
    """Merkezin km doğusundaki boylam (paket kutusuyla aynı ölçü)."""
    import math
    return HLON + km / (mpi.KM_PER_DEG * math.cos(math.radians(HLAT)))


def _halka_kabi(yol, merkez=(HLAT, HLON), pack_id='sinop_tr', renk=(40, 90, 60), atla=()):
    """Gerçek halka kuralıyla (üretim aracının karo seçimiyle) küçük bir kap: merkezden doğuya
    giden şeridin her düzeyde karosu (halka içindekiler; z9-z11 bütün şerit)."""
    a = _arac()
    bbox = MP.daire_bbox(merkez[0], merkez[1], MP.SITE_RADIUS_KM)
    kural = a.duzey_kurali()
    halka = {h['zoom']: set(a.halka_karolari(h['zoom'], merkez, h['radius_km'], bbox))
             for h in kural['rings']}
    tam = _webp(renk)
    karolar = {}
    for km in range(0, 96, 2):
        lon = merkez[1] + km / (mpi.KM_PER_DEG * np.cos(np.radians(merkez[0])))
        for z in range(9, 14):
            x, y = tile_cache.lonlat_to_tile(z, lon, merkez[0])
            if z > kural['full_zoom_max'] and (x, y) not in halka[z]:
                continue
            if (z, x, y) not in atla:
                karolar[(z, x, y)] = (10000, tam)
    meta = _meta(pack_id=pack_id, bounds=','.join('%.9f' % v for v in a.alan_kutusu(a.alan_karolari(bbox))),
                 detail=json.dumps({'center': list(merkez), 'full_zoom_max': kural['full_zoom_max'],
                                    'rings': kural['rings']}))
    return _kap(yol, karolar, meta), halka


def test_halka_kurali_sabitleri_ve_tek_olcu():
    assert mpi.IMAGERY_FULL_ZOOM_MAX == 11 and mpi.IMAGERY_RINGS == ((12, 50.0), (13, 25.0))
    assert mpi.MAX_UPSAMPLE_LEVELS == mpi.READER_MAX_ZOOM - mpi.IMAGERY_FULL_ZOOM_MAX == 4
    w, s_, e, n = MP.daire_bbox(HLAT, HLON, 100.0)               # paket kutusu aynı ölçüyle
    assert abs((n - HLAT) * mpi.KM_PER_DEG - 100.0) < 1e-9
    assert [round(mpi.piksel_metre(z), 2) for z in (11, 12, 13)] == [30.57, 15.29, 7.64]
    # Tek tanım: 111,32 sayısı yalnız map_pack_imagery'de
    for ad in ('map_packs.py', 'map_pack_imagery.py'):
        metin = open(os.path.join(DEPO, 'hrma', 'analysis', ad), encoding='utf-8').read()
        assert metin.count('111.32') == (1 if ad == 'map_pack_imagery.py' else 0), ad


def test_halka_karolari_okuyucuyla_ayni_karar(tmp_path):
    yol, halka = _halka_kabi(tmp_path / 'h.sqlite')
    ok = mpi.GoruntuOkuyucu(yol)
    try:
        for z, karolar in halka.items():
            r = dict(mpi.IMAGERY_RINGS)[z]
            assert karolar and all(ok.duzeyde_mi(z, x, y) for x, y in karolar)
            # Halkaya değen karonun komşusu halkada değilse okuyucu da öyle der
            dis = [(x + 1, y) for x, y in karolar if (x + 1, y) not in karolar]
            assert dis and not any(ok.duzeyde_mi(z, x, y) for x, y in dis)
            # Halka karolarının merkeze en yakın noktası yarıçap içinde, en uzak değil
            for x, y in karolar:
                assert mpi.karo_halkada_mi(z, x, y, HLAT, HLON, r)
    finally:
        ok.kapat()


@pytest.mark.parametrize('km,beklenen_duzey', [(0, 13), (20, 13), (35, 12), (45, 12), (70, 11), (90, 11)])
def test_halka_disinda_kaba_duzeyin_atasi(tmp_path, km, beklenen_duzey):
    yol, _h = _halka_kabi(tmp_path / 'h.sqlite')
    ok = mpi.GoruntuOkuyucu(yol)
    try:
        lon = _dogu(km)
        for z in (13, 14, 15):
            x, y = tile_cache.lonlat_to_tile(z, lon, HLAT)
            assert ok.kaynak_duzeyi(z, x, y) == beklenen_duzey, (km, z)
            a = ok.karo_veya_ata(z, x, y, mpi.MAX_UPSAMPLE_LEVELS)
            assert a is not None and a.z == beklenen_duzey and a.dz == z - beklenen_duzey, (km, z)
            assert a.pencere[2] == 512 >> a.dz and a.coverage == 10000
            if a.dz > 0:
                assert ok.karo_veya_ata(z, x, y, a.dz - 1) is None       # büyütme tavanı
            # Ata, aynı mozaiğin kaba düzeyi: kendi kaynak düzeyindeki karonun aynısı
            assert a.veri == ok.karo(a.z, a.x, a.y)
    finally:
        ok.kapat()


def test_halka_icinde_verisiz_karo_kaba_duzeye_inmez(tmp_path):
    x13, y13 = tile_cache.lonlat_to_tile(13, HLON, HLAT)
    yol, _h = _halka_kabi(tmp_path / 'v.sqlite', atla={(13, x13, y13)})
    ok = mpi.GoruntuOkuyucu(yol)
    try:
        assert ok.kaynak_duzeyi(13, x13, y13) == 13
        assert ok.karo_veya_ata(13, x13, y13) is None                     # veri yok: boş kalır
        assert ok.karo_veya_ata(15, 4 * x13 + 1, 4 * y13 + 2) is None
    finally:
        ok.kapat()


def test_kutu_disi_ve_zoom_min_alti_none(tmp_path):
    yol, _h = _halka_kabi(tmp_path / 'k.sqlite')
    ok = mpi.GoruntuOkuyucu(yol)
    try:
        x, y = tile_cache.lonlat_to_tile(13, HLON + 5.0, HLAT)
        assert ok.kaynak_duzeyi(13, x, y) is None and ok.karo_veya_ata(13, x, y) is None
        x8, y8 = tile_cache.lonlat_to_tile(8, HLON, HLAT)
        assert ok.karo_veya_ata(8, x8, y8) is None
    finally:
        ok.kapat()


def test_saglayici_ust_uste_paketlerde_en_ince_tam_karo(tmp_path):
    """A (Sinop merkezi) ve B (35 km doğusu): B'nin rampası yanında A'nın yalnız z12'si var;
    sağlayıcı yol sırasından bağımsız B'nin z13 karosunu verir (A önce sıralansa da)."""
    a_yol, _ = _halka_kabi(tmp_path / 'a.sqlite', renk=(200, 0, 0))
    b_yol, _ = _halka_kabi(tmp_path / 'b.sqlite', merkez=(HLAT, _dogu(35)), pack_id='ksc_lc39a',
                           renk=(0, 200, 0))
    x, y = tile_cache.lonlat_to_tile(13, _dogu(36), HLAT)
    alinan = []
    try:
        fn = mpi.saglayici(lambda: [(a_yol, _sha(a_yol)), (b_yol, _sha(b_yol))],
                           buyutucu=lambda ata: alinan.append(ata) or b'buyutuldu')
        ob = mpi.GoruntuOkuyucu(b_yol)
        try:
            assert fn(13, x, y) == ob.karo(13, x, y)                      # B, dz=0
        finally:
            ob.kapat()
        assert alinan == []
        # B'nin halkası dışında (A'nın rampası) A'nın z13'ü
        xa, ya = tile_cache.lonlat_to_tile(13, HLON, HLAT)
        oa = mpi.GoruntuOkuyucu(a_yol)
        try:
            assert fn(13, xa, ya) == oa.karo(13, xa, ya)
        finally:
            oa.kapat()
    finally:
        mpi.okuyuculari_birak()


def test_kanca_halka_disinda_z15_atadan_opak(tmp_path, monkeypatch):
    """Uçtan uca (map_packs sağlayıcısı): rampadan 70 km uzakta z15 karo = z11 atasının 32 px
    penceresinin büyütülmesi; zemin opak, boşluk yok; rampada z13 atası (128 px)."""
    yol, _h = _halka_kabi(tmp_path / 'u.sqlite')
    monkeypatch.setattr(MP, 'kurulu_goruntu_kaynaklari', lambda m=None: [(yol, _sha(yol))])
    monkeypatch.setattr(MP, '_ZEMIN_SAGLAYICI', None)
    alinan = []
    gercek = MP._goruntu_buyut
    monkeypatch.setattr(MP, '_goruntu_buyut', lambda ata: alinan.append(ata) or gercek(ata))
    try:
        MP.goruntu_zemini_kaydet()
        for km, z_kaynak in ((70, 11), (0, 13)):
            x, y = tile_cache.lonlat_to_tile(15, _dogu(km), HLAT)
            b = MP._ZEMIN_SAGLAYICI(15, x, y)
            assert alinan[-1].z == z_kaynak and alinan[-1].pencere[2] == 512 >> (15 - z_kaynak)
            with Image.open(io.BytesIO(b)) as im:
                assert im.size == (512, 512) and im.mode == 'RGB'
                assert np.all(np.abs(np.asarray(im).reshape(-1, 3).mean(0) - (40, 90, 60)) <= 6)
    finally:
        mpi.okuyuculari_birak()


def test_alan_istatistigi_halka_kapisi_ayri(arac):
    """Kutunun bütünü geçse de halkada bulut kalıntısı eşiği aşarsa kapı GEÇMEZ; halka bloğunda
    alt alan istatistiği yoksa adıyla durur."""
    plan = {'bbox': list(_hkutu()), 'merkez': [HLAT, HLON], 'duzey_kurali': arac.duzey_kurali()}
    halkalar = arac.halka_plani(plan)
    hb = arac.halka_bloklari(halkalar)
    bos = {'ic_px': 0, 'dolu_px': 0, 'bos_gozlenmis_px': 0, 'bos_gozlenmemis_px': 0, 'beyaz_px': 0,
           'su_bulut_px': 0, 'kiyi_kabul_px': 0, 'kalici_parlak_su_px': 0, 'katki': {}}
    bitti = {}
    for i, b in enumerate(sorted(hb) + [(0, 0), (1, 0)]):
        ist = dict(bos, ic_px=1000, dolu_px=1000, katki={'g': 1000})
        if b in hb:
            ist['alanlar'] = {'z12': dict(bos, ic_px=100, dolu_px=100),
                              'z13': dict(bos, ic_px=10, dolu_px=8, bos_gozlenmis_px=2 if i == 0 else 0)}
        bitti[b] = ist
    alan, katki = arac.alan_istatistigi(bitti, halkalar)
    assert alan['kutu']['kapi']['gecti'] and alan['z12']['kapi']['gecti']
    assert not alan['z13']['kapi']['gecti']                      # 2 / (8n+2) > %0,5
    assert alan['z13']['karo'] == len(halkalar[13]) and katki == {'g': 1000 * len(bitti)}
    del bitti[sorted(hb)[0]]['alanlar']
    with pytest.raises(SystemExit):
        arac.alan_istatistigi(bitti, halkalar)


def test_blok_halka_maskeleri_karo_sayisiyla_tutarli(arac):
    plan = {'bbox': list(_hkutu()), 'merkez': [HLAT, HLON], 'duzey_kurali': arac.duzey_kurali()}
    halkalar = arac.halka_plani(plan)
    toplam = {12: 0, 13: 0}
    for bx, by in arac.halka_bloklari(halkalar):
        m = arac.blok_halka_maskeleri(halkalar, bx, by)
        for z in (12, 13):
            toplam[z] += int(m['z%d' % z].sum())
            assert not (m['z13'] & ~m['z12']).any()                # ince halka kabanın içinde
    assert toplam[13] == len(halkalar[13]) * 512 * 512
    assert toplam[12] == len(halkalar[12]) * 1024 * 1024
