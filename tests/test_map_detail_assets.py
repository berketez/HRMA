"""Harita ayrıntısı F1 veri hattının bekçileri (K1, 7 Eki 2026).

Araç: ``tools/build_map_detail_assets.py``. Tasarım:
``docs/scofield/raw/OH/UI/harita-detay/tasarim.md`` §2.1, §3.2, §3.3, §5.1.

Bekçilerin yakaladığı arıza sınıfları:

* **Kanıtsız kaynak.** sha256'sı ``SHA256SUMS.txt`` ile tutmayan ya da
  GeoJSON imzası taşımayan dosyadan varlık üretilmez.
* **Geometri bozulması.** Hücre bölmesi yeni köşe üretmez, kesim kaybetmez,
  kesimi iki kez yazmaz; ikili biçim bağımsız bir ayrıştırıcıyla geri okunur.
* **Bütçe aşımı.** Toplam bütçeyi aşarsa HİÇBİR dosya yazılmaz.
* **Ürün kararı kayması.** Sınır görünümü tek sabitle seçilir ve varsayılandır;
  ``POP_MAX`` dosyaya yazılmaz (tasarım §5.3-4).

Küçük sentetik GeoJSON girdileri TEST ALTYAPISIDIR (fixture); kullanıcıya
gösterilen veri değildir ve depoya varlık olarak girmez.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import struct
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
for _yol in (str(KOK), str(KOK / 'tools')):
    if _yol not in sys.path:
        sys.path.insert(0, _yol)

import build_map_detail_assets as hat  # noqa: E402
from hrma.analysis import tile_cache  # noqa: E402

GERCEK_KAYNAK = hat.VARSAYILAN_KAYNAK
VARLIK_DIZIN = KOK / 'hrma' / 'static' / 'map'


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _ozellik(geometri, **ozellikler):
    return {'type': 'Feature', 'properties': ozellikler, 'geometry': geometri}


def _yaz_geojson(yol: pathlib.Path, ozellikler: list) -> None:
    metin = json.dumps({'type': 'FeatureCollection', 'features': ozellikler})
    # Kanıt sözleşmesinin "en az bayt" eşiğini geçsin diye sonuna boşluk;
    # JSON olarak geçerli kalır.
    eksik = hat.NE_EN_AZ_BAYT - len(metin)
    yol.write_text(metin + ' ' * max(eksik + 16, 0), encoding='utf-8')


def _sentetik_kaynak(kok: pathlib.Path) -> pathlib.Path:
    """Aracın okuduğu bütün dosyaların küçük, kurgusal bir kopyası."""
    ne = kok / hat.NE_ALT_DIZIN
    ne.mkdir(parents=True)
    cizgi = {'type': 'LineString',
             'coordinates': [[30.0, 40.0], [35.5, 40.0], [37.0, 41.0], [37.0, 41.0]]}
    halka = {'type': 'Polygon',
             'coordinates': [[[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 10.0]]]}
    for basamak in hat.BASAMAKLAR.values():
        for katman, dosya in basamak.items():
            g = halka if katman == 'lakes' else cizgi
            _yaz_geojson(ne / dosya, [_ozellik(g, min_zoom=4.7),
                                      _ozellik(None, min_zoom=1)])
    yerler = [
        _ozellik({'type': 'Point', 'coordinates': [32.86, 39.93]},
                 NAME='Ankara', NAME_EN='Ankara', NAME_TR='Ankara', MIN_ZOOM=3,
                 LABELRANK=2, FEATURECLA='Admin-0 capital', ADM0_A3='TUR',
                 POP_MAX=1000, NE_ID=1, ADM1NAME='Ankara'),
        _ozellik({'type': 'Point', 'coordinates': [28.97, 41.01]},
                 NAME='Istanbul', NAME_EN='Istanbul', NAME_TR='İstanbul', MIN_ZOOM=2,
                 LABELRANK=1, FEATURECLA='Admin-1 capital', ADM0_A3='TUR',
                 POP_MAX=9000, NE_ID=2, ADM1NAME='Istanbul'),
        _ozellik({'type': 'Point', 'coordinates': [35.15, 42.02]},
                 NAME='Sinop', NAME_EN='Sinop', NAME_TR='', MIN_ZOOM=7,
                 LABELRANK=8, FEATURECLA='Admin-1 capital', ADM0_A3='TUR',
                 POP_MAX=50, NE_ID=3, ADM1NAME='Sinop'),
    ]
    _yaz_geojson(ne / hat.YERLER_DOSYASI, yerler)
    for dosya in hat.SINIR_GORUNUMU_DOSYALARI.values():
        _yaz_geojson(ne / dosya, [_ozellik(
            halka, NAME='Turkey', NAME_EN='Turkey', NAME_TR='Türkiye',
            LABEL_X=34.5, LABEL_Y=39.0, MIN_LABEL=2, MAX_LABEL=7, LABELRANK=2,
            ADM0_A3='TUR')])
    satirlar = []
    for yol in sorted(ne.iterdir()):
        ozet = hashlib.sha256(yol.read_bytes()).hexdigest()
        satirlar.append('%s  %s/%s' % (ozet, hat.NE_ALT_DIZIN, yol.name))
    (kok / hat.SHA_LISTESI).write_text('\n'.join(satirlar) + '\n', encoding='utf-8')
    return kok


def _sentetik_110m(kok: pathlib.Path) -> pathlib.Path:
    yol = kok / 'earth_borders.json'
    yol.write_text(json.dumps({
        'source': 'test', 'license': 'test', 'retrieved_utc': 'test',
        'format': 'test', 'point_count': 5,
        'layers': {'borders': [[0.0, 0.0, 1.0, 1.0]],
                   'coastline': [[-170.0, 5.0, -100.0, 5.0, -100.0, 5.0]]}}),
        encoding='utf-8')
    return yol


def hmv1_oku(veri: bytes, katman_ozeti: dict) -> dict:
    """Bağımsız HMV1 ayrıştırıcı: {katman: [[(lon_q, lat_q), ...], ...]}."""
    assert veri[:4] == b'HMV1'
    bloklar, toplam_kose, toplam_cizgi = struct.unpack_from('<III', veri, 4)
    sonuc = {}
    sayilan_blok = sayilan_kose = sayilan_cizgi = 0
    for ad, katman in katman_ozeti.items():
        cizgiler = []
        for h in katman['cells']:
            nv, nl, ofset = h['vertex_count'], h['line_count'], h['offset']
            assert ofset % 4 == 0, 'blok 4 bayta hizalı değil'
            xs = struct.unpack_from('<%di' % (2 * nv), veri, ofset)
            uz = struct.unpack_from('<%dI' % nl, veri, ofset + 8 * nv)
            mz = veri[ofset + 8 * nv + 4 * nl: ofset + 8 * nv + 5 * nl]
            assert len(mz) == nl
            assert sum(uz) == nv
            i = 0
            for n in uz:
                cizgiler.append([(xs[2 * k], xs[2 * k + 1]) for k in range(i, i + n)])
                i += n
            sayilan_blok += 1
            sayilan_kose += nv
            sayilan_cizgi += nl
        sonuc[ad] = cizgiler
    assert (sayilan_blok, sayilan_kose, sayilan_cizgi) == (bloklar, toplam_kose, toplam_cizgi)
    return sonuc


def _kesimler(cizgiler):
    return [(a, b) for c in cizgiler for a, b in zip(c, c[1:])]


# ---------------------------------------------------------------------------
# Geometri ve biçim
# ---------------------------------------------------------------------------

def test_hucre_bolmesi_yeni_kose_uretmez_kesim_kaybetmez():
    q = hat.nicemle
    # 36° ızgarada üç hücreye değen çizgi: (5,1) -> (6,0) -> (7,1).
    # Son köşe tek başına bir parça açmaz; (6,0) parçası onunla biter.
    noktalar = [(q(30), q(40)), (q(35), q(50)), (q(40), q(56)), (q(70), q(56)),
                (q(73), q(50))]
    parcalar = hat.cizgiyi_hucrelere_bol(noktalar)
    assert [h for h, _ in parcalar] == [(5, 1), (6, 0)]
    assert hat.hucre(*noktalar[-1]) == (7, 1)
    yeni = {p for _, parca in parcalar for p in parca} - set(noktalar)
    assert not yeni, 'bölme yeni köşe üretti: %r' % yeni
    kesimler = _kesimler([parca for _, parca in parcalar])
    assert kesimler == list(zip(noktalar, noktalar[1:])), \
        'kesim kaybı ya da tekrarı var'
    for h, parca in parcalar:
        assert hat.hucre(*parca[0]) == h, 'parça kendi hücresinde başlamıyor'


def test_hmv1_gidis_donus_ve_kutu():
    t = hat.KatmanToplayici()
    t.ekle([(30.0, 40.0), (35.0, 40.0), (40.0, 41.0)], 47)
    t.ekle([(-179.9, -39.0), (179.9, -39.2)], hat.MIN_ZOOM_YOK)
    veri, ozet = hat.basamak_ikilisi({'coastline': t})
    okunan = hmv1_oku(veri, ozet['layers'])['coastline']
    q = hat.nicemle
    beklenen = [[(q(30), q(40)), (q(35), q(40)), (q(40), q(41))],
                [(q(-179.9), q(-39)), (q(179.9), q(-39.2))]]
    assert sorted(_kesimler(okunan)) == sorted(_kesimler(beklenen))
    for h in ozet['layers']['coastline']['cells']:
        w, s, e, n = h['bbox']
        assert w <= e and s <= n
    # min_zoom kodu: 4.7 -> 47, yok -> 255
    tum_mz = []
    for h in ozet['layers']['coastline']['cells']:
        o = h['offset'] + 8 * h['vertex_count'] + 4 * h['line_count']
        tum_mz.extend(veri[o:o + h['line_count']])
    assert 47 in tum_mz and hat.MIN_ZOOM_YOK in tum_mz
    # Kaynak alanından kodlama: küçük/büyük harfli anahtar, ondalık korunur.
    assert hat.min_zoom_kodla({'min_zoom': 4.7}) == 47
    assert hat.min_zoom_kodla({'MIN_ZOOM': 6.3}) == 63
    assert hat.min_zoom_kodla({'min_zoom': None}) == hat.MIN_ZOOM_YOK
    assert hat.min_zoom_kodla({}) == hat.MIN_ZOOM_YOK


def test_hucre_izgarasi_tile_cache_ile_ayni(tmp_path):
    dosyalar, _ = hat.uret(_sentetik_kaynak(tmp_path / 'k'), _sentetik_110m(tmp_path),
                           butce=10 ** 9)
    m = json.loads(dosyalar['vectors_manifest.json'])
    mw, mh = tile_cache.matrix_size(hat.HUCRE_Z)
    assert (m['cell_grid']['matrix_width'], m['cell_grid']['matrix_height']) == (mw, mh)
    assert m['cell_grid']['span_deg'] == tile_cache.tile_span_deg(hat.HUCRE_Z) == 36.0
    for basamak in hat.BASAMAK_SIRASI:
        b = m['levels'][basamak]
        veri = dosyalar[b['file']]
        assert b['bytes'] == len(veri)
        assert b['sha256'] == hashlib.sha256(veri).hexdigest()
        hmv1_oku(veri, b['layers'])
        for katman in b['layers'].values():
            for h in katman['cells']:
                cx, cy = h['cell']
                assert 0 <= cx < mw and 0 <= cy < mh


# ---------------------------------------------------------------------------
# Kaynak kanıtı
# ---------------------------------------------------------------------------

def test_sha_tutmazsa_uretim_durur(tmp_path):
    kok = _sentetik_kaynak(tmp_path / 'k')
    hedef = kok / hat.NE_ALT_DIZIN / hat.YERLER_DOSYASI
    hedef.write_text(hedef.read_text(encoding='utf-8').replace('Sinop', 'Sinoq'),
                     encoding='utf-8')
    with pytest.raises(hat.KaynakHatasi, match='sha256 tutmadı'):
        hat.uret(kok, _sentetik_110m(tmp_path), butce=10 ** 9)


def test_listede_olmayan_dosya_kullanilmaz(tmp_path):
    kok = _sentetik_kaynak(tmp_path / 'k')
    liste = kok / hat.SHA_LISTESI
    liste.write_text('\n'.join(s for s in liste.read_text().splitlines()
                               if hat.YERLER_DOSYASI not in s) + '\n')
    with pytest.raises(hat.KaynakHatasi, match='listesinde yok'):
        hat.uret(kok, _sentetik_110m(tmp_path), butce=10 ** 9)


def test_geojson_imzasi_yoksa_durur(tmp_path):
    kok = _sentetik_kaynak(tmp_path / 'k')
    hedef = kok / hat.NE_ALT_DIZIN / hat.YERLER_DOSYASI
    hedef.write_bytes(b'<html>hata</html>' + b' ' * hat.NE_EN_AZ_BAYT)
    liste = kok / hat.SHA_LISTESI
    satirlar = [('%s  %s/%s' % (hashlib.sha256(hedef.read_bytes()).hexdigest(),
                                hat.NE_ALT_DIZIN, hat.YERLER_DOSYASI))
                if hat.YERLER_DOSYASI in s else s
                for s in liste.read_text().splitlines()]
    liste.write_text('\n'.join(satirlar) + '\n')
    with pytest.raises(hat.KaynakHatasi, match='imzası'):
        hat.uret(kok, _sentetik_110m(tmp_path), butce=10 ** 9)


# ---------------------------------------------------------------------------
# Bütçe ve belirlenimcilik
# ---------------------------------------------------------------------------

def test_butce_asilirsa_hicbir_dosya_yazilmaz(tmp_path, monkeypatch):
    kok = _sentetik_kaynak(tmp_path / 'k')
    cikti = tmp_path / 'cikti'
    monkeypatch.setattr(hat, 'BOYUT_BUTCESI_BAYT', 1000)
    kod = hat.main(['--kaynak', str(kok), '--cikti', str(cikti)])
    assert kod == 2
    assert not cikti.exists() or not any(cikti.iterdir()), \
        'bütçe aşıldığı halde dosya yazıldı'


def test_butce_icindeyse_yazar_ve_toplam_butceyi_asmaz(tmp_path):
    kok = _sentetik_kaynak(tmp_path / 'k')
    cikti = tmp_path / 'cikti'
    assert hat.main(['--kaynak', str(kok), '--cikti', str(cikti)]) == 0
    adlar = sorted(p.name for p in cikti.iterdir())
    assert adlar == sorted(['vectors_110m.bin', 'vectors_50m.bin', 'vectors_10m.bin',
                            'vectors_manifest.json', 'places.json',
                            'country_labels.json'])
    toplam = sum(p.stat().st_size for p in cikti.iterdir())
    m = json.loads((cikti / 'vectors_manifest.json').read_text(encoding='utf-8'))
    assert toplam <= m['budget']['limit_bytes'] == hat.BOYUT_BUTCESI_BAYT


def test_cikti_belirlenimci(tmp_path):
    kok = _sentetik_kaynak(tmp_path / 'k')
    eski = _sentetik_110m(tmp_path)
    a, _ = hat.uret(kok, eski, butce=10 ** 9)
    b, _ = hat.uret(kok, eski, butce=10 ** 9)
    assert a == b


# ---------------------------------------------------------------------------
# Öznitelikler ve ürün kararları
# ---------------------------------------------------------------------------

def test_sinir_gorunumu_varsayilan_ve_tek_sabit(tmp_path):
    assert hat.SINIR_GORUNUMU == 'varsayilan', \
        'Berke kararı gelmeden sınır görünümü değişmez (§28-20)'
    dosyalar, _ = hat.uret(_sentetik_kaynak(tmp_path / 'k'), _sentetik_110m(tmp_path),
                           butce=10 ** 9)
    m = json.loads(dosyalar['vectors_manifest.json'])
    assert m['provenance']['boundary_view'] == 'varsayilan'
    assert m['provenance']['boundary_view_file'] == 'ne_10m_admin_0_countries.geojson'
    kullanilan = {k['file'] for k in m['sources']}
    assert 'ne_10m_admin_0_countries_tur.geojson' not in kullanilan


def test_yerler_oncelik_sirasi_ve_pop_max_yazilmaz(tmp_path):
    dosyalar, olcum = hat.uret(_sentetik_kaynak(tmp_path / 'k'), _sentetik_110m(tmp_path),
                               butce=10 ** 9)
    yerler = json.loads(dosyalar['places.json'])
    assert yerler['fields'] == ['lon', 'lat', 'name', 'name_en', 'name_tr', 'min_zoom',
                                'labelrank', 'featurecla', 'adm0']
    assert all(len(r) == len(yerler['fields']) for r in yerler['rows'])
    nufus = {1000, 9000, 50}       # sentetik POP_MAX değerleri
    assert not any(v in nufus for r in yerler['rows'] for v in r[5:]), \
        'POP_MAX dosyaya sızdı (tasarım §5.3-4)'
    adlar = [r[2] for r in yerler['rows']]
    assert adlar == ['Ankara', 'Istanbul', 'Sinop'], 'başkent önce, sonra LABELRANK'
    ist = yerler['rows'][1]
    assert ist[4] == 'İstanbul' and ist[3] == 'Istanbul'
    sinop = yerler['rows'][2]
    assert sinop[4] is None, 'boş NAME_TR null olarak kalmalı (istemci NAME yedeğine düşer)'
    assert olcum['yer']['name_tr_fallback_to_name'] == 1
    assert olcum['yer']['turkey_province_centre_count'] == 3


# ---------------------------------------------------------------------------
# Gerçek kaynak (depo dışı; yoksa gerekçeli atlama — docs kanıtı değil,
# yapım girdisidir)
# ---------------------------------------------------------------------------

gercek_kaynak = pytest.mark.skipif(
    not (GERCEK_KAYNAK / hat.SHA_LISTESI).is_file(),
    reason='Natural Earth ham verisi bu makinede yok (%s); yapım girdisi' % GERCEK_KAYNAK)


@gercek_kaynak
def test_gercek_kaynak_olculen_gercekler():
    dosyalar, olcum = hat.uret(GERCEK_KAYNAK, butce=10 ** 9)
    m = json.loads(dosyalar['vectors_manifest.json'])
    beklenen_liste = hat.sha_listesini_oku(GERCEK_KAYNAK)
    for k in m['sources']:
        assert beklenen_liste['%s/%s' % (hat.NE_ALT_DIZIN, k['file'])] == k['sha256']
        assert k['version'] == 'v5.1.2'
    # 110m, depodaki earth_borders.json'dan: kesim kümesi birebir korunur.
    eski = json.loads(hat.ESKI_110M.read_text(encoding='utf-8'))
    okunan = hmv1_oku(dosyalar['vectors_110m.bin'], m['levels']['110m']['layers'])
    for katman in ('coastline', 'borders'):
        q = hat.nicemle
        kaynak_kesim = []
        for duz in eski['layers'][katman]:
            c = [(q(duz[i]), q(duz[i + 1])) for i in range(0, len(duz) - 1, 2)]
            c = [p for j, p in enumerate(c) if j == 0 or p != c[j - 1]]
            kaynak_kesim.extend(zip(c, c[1:]))
        assert sorted(_kesimler(okunan[katman])) == sorted(kaynak_kesim), \
            '%s: 110m kesim kümesi korunmadı' % katman
    yer = olcum['yer']
    assert yer['place_count'] == 7342
    assert yer['turkey_province_centre_count'] == 70
    yerler = json.loads(dosyalar['places.json'])
    tr = {r[4]: r for r in yerler['rows'] if r[8] == 'TUR'}
    for ad in ('İstanbul', 'İzmir', 'Çanakkale', 'Ankara', 'Şanlıurfa', 'Muğla'):
        assert ad in tr, '%s TR adıyla yok' % ad
    assert tr['İstanbul'][3] == 'Istanbul'
    assert m['places']['name_tr_fill_ratio'] == yer['name_tr_fill_ratio']


@gercek_kaynak
def test_gercek_kaynak_butce_bekcisi_olcer():
    """Varsayılan bütçeyle üretim ya bütçe içinde kalır ya da DURUR."""
    try:
        dosyalar, olcum = hat.uret(GERCEK_KAYNAK)
    except hat.ButceAsildi as e:
        assert 'HİÇBİR DOSYA YAZILMADI' in str(e)
        return
    assert sum(len(v) for v in dosyalar.values()) <= hat.BOYUT_BUTCESI_BAYT


# ---------------------------------------------------------------------------
# Depodaki varlıklar
# ---------------------------------------------------------------------------

def test_depodaki_varliklar_ya_tutarli_ya_butce_durdu():
    """Varlık YA depoda ve manifestle tutarlıdır YA DA yokluğu ölçülmüş bir
    bütçe durmasıyla açıklanır. Üçüncü hâl (bütçe geçiyor ama varlık
    commit'lenmemiş, ya da varlık var ama bozuk) KIRMIZIDIR.

    K1 (7 Eki): gerçek kaynakla toplam 12.670.753 B > 12.000.000 B; araç
    durdu, varlık yazılmadı, karar ana modelde (rapor.md K1).
    """
    assert (KOK / 'hrma' / 'static' / 'img' / 'earth_borders.json').is_file(), \
        '110m yedek katmanı silinmemeli'
    manifest = VARLIK_DIZIN / 'vectors_manifest.json'
    if not manifest.is_file():
        if not (GERCEK_KAYNAK / hat.SHA_LISTESI).is_file():
            pytest.skip('varlık yok ve ham kaynak bu makinede yok; yokluğun '
                        'gerekçesi (bütçe durması) burada ölçülemez')
        with pytest.raises(hat.ButceAsildi):
            hat.uret(GERCEK_KAYNAK)
        return
    m = json.loads(manifest.read_text(encoding='utf-8'))
    toplam = manifest.stat().st_size
    for b in m['levels'].values():
        veri = (VARLIK_DIZIN / b['file']).read_bytes()
        assert hashlib.sha256(veri).hexdigest() == b['sha256']
        hmv1_oku(veri, b['layers'])
        toplam += len(veri)
    for anahtar in ('places', 'country_labels'):
        veri = (VARLIK_DIZIN / m[anahtar]['file']).read_bytes()
        assert hashlib.sha256(veri).hexdigest() == m[anahtar]['sha256']
        toplam += len(veri)
    assert toplam <= hat.BOYUT_BUTCESI_BAYT


# ---------------------------------------------------------------------------
# F1 denetimi Ş3 (a, d) ve Türkçe adlar, karar §28-45 (13 Eki 2026)
# ---------------------------------------------------------------------------
# Kâhin: ham Natural Earth v5.1.2 + karar §28-45'in tablosu (aşağıda, görev
# metninden; üreticinin AD_DUZELTMELERI'nden OKUNMAZ). Tablo dışındaki her ad
# ve alan ham NE ile bit-aynı olmalı.

#: (katman, NE kararlı anahtarı) -> {alan: (ham NE değeri, yeni değer)}.
KARAR_28_45 = {
    ('country_labels', 'TUR'): {'name_en': ('Turkey', 'Türkiye')},
    ('country_labels', 'CYP'): {'name_tr': ('Kıbrıs Cumhuriyeti', 'Güney Kıbrıs Rum Yönetimi'),
                                'name_en': ('Cyprus',
                                            'Greek Cypriot Administration of Southern Cyprus')},
    ('country_labels', 'ESB'): {'name_tr': ('Dhekelia Kantonu', 'Dikelya'),
                                'name_en': ('Dhekelia Cantonment',
                                            'Dhekelia Sovereign Base Area')},
    ('places', 1159127441): {'name': ('Elâzığ', 'Elazığ'),               # TUR Elazığ
                             'name_tr': ('Elâzığ', 'Elazığ')},
    ('places', 1159144591): {'name': ('Stepanakert', 'Xankəndi'),        # AZE
                             'name_en': ('Stepanakert', 'Khankendi')},
    ('places', 1159134155): {'name_tr': ('Simferopol', 'Akmescit'),      # Kırım
                             'adm0': ('RUS', 'UKR')},
    ('places', 1159134145): {'name_tr': ('Evpatorya', 'Gözleve'),        # Kırım
                             'adm0': ('RUS', 'UKR')},
    # Karar §28-45/Kırım: Kırım yerleşimlerinin ülke kodu (Türkiye'nin resmî
    # görüşü). Görev metnindeki liste: Sevastopol, Kerch, Yalta, Dzhankoy.
    ('places', 1159150561): {'adm0': ('RUS', 'UKR')},                   # Sevastopol
    ('places', 1159134151): {'adm0': ('RUS', 'UKR')},                   # Kerch
    ('places', 1159147519): {'adm0': ('RUS', 'UKR')},                   # Yalta
    ('places', 1159134141): {'adm0': ('RUS', 'UKR')},                   # Dzhankoy
    ('places', 1159140707): {'name_tr': ('Turfan İli', 'Turfan')},       # CHN
    ('places', 1159126219): {'name_tr': ('Hasiçi', 'Haseke')},           # SYR
    ('places', 1159126193): {'name_tr': ('İdlip', 'İdlib')},             # SYR
    ('places', 1159136459): {'name_tr': ('Celal-Abad', 'Celalabad')},    # KGZ
    ('places', 1159134335): {'name_tr': ('Karşi', 'Karşı')},             # UZB
    ('places', 1159151263): {'name_tr': ('Bükreș', 'Bükreş')},           # ROU
    ('places', 1159149403): {'name_tr': ('Yaș', 'Yaş')},                 # ROU
    ('places', 1159135835): {'name_tr': ('Temeșvar', 'Temeşvar')},       # ROU
    ('places', 1159127789): {'name_tr': ('Tulca', 'Tulça')},             # ROU
}
#: Değişmeyeceği karar metninde ADIYLA yazılanlar (alan: ham NE değeri).
KARAR_28_45_DEGISMEZ = {
    ('country_labels', 'CYN'): {'name_tr': 'Kuzey Kıbrıs Türk Cumhuriyeti',
                                'name_en': 'Turkish Republic of Northern Cyprus'},
    ('country_labels', 'WSB'): {'name_tr': 'Ağrotur'},
    ('country_labels', 'CNM'): {'name_tr': 'Yeşil Hat'},
    ('places', 1159127697): {'name': 'Hakkâri', 'name_tr': 'Hakkâri'},   # TDK yazımı
    ('places', 1159144591): {'name_tr': 'Hankendi'},
}
_NE_AD = {'name': 'NAME', 'name_en': 'NAME_EN', 'name_tr': 'NAME_TR', 'adm0': 'ADM0_A3'}


def _ad(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _say(v):
    return None if v is None else float(v)


@pytest.fixture(scope='module')
def ham_ne():
    if not (GERCEK_KAYNAK / hat.SHA_LISTESI).is_file():
        pytest.skip('Natural Earth ham verisi bu makinede yok (%s); yapım girdisi'
                    % GERCEK_KAYNAK)
    ne = GERCEK_KAYNAK / hat.NE_ALT_DIZIN
    yer = json.loads((ne / 'ne_10m_populated_places.geojson').read_text(encoding='utf-8'))
    ulke = json.loads((ne / 'ne_10m_admin_0_countries.geojson').read_text(encoding='utf-8'))
    return {'places': [f for f in yer['features']
                       if (f.get('geometry') or {}).get('type') == 'Point'],
            'country_labels': [f['properties'] for f in ulke['features']
                               if f['properties'].get('LABEL_X') is not None
                               and f['properties'].get('LABEL_Y') is not None]}


@pytest.fixture(scope='module')
def gercek_uretim(ham_ne):
    dosyalar, _ = hat.uret(GERCEK_KAYNAK, butce=10 ** 9)
    return {ad: json.loads(dosyalar[ad]) for ad in ('places.json', 'country_labels.json')}


def _beklenen(ham_ne, kahin=True) -> dict:
    """Ham NE'den beklenen satırlar (alan sırası varlıktaki gibi), kâhin
    tablosu uygulanmış. Koordinat 1e-5° (5 ondalık, tasarım §3.2)."""
    yerler = []
    for f in ham_ne['places']:
        p = f['properties']
        lon, lat = f['geometry']['coordinates'][:2]
        k = {a: _ad(p.get(n)) for a, n in _NE_AD.items()}
        for a, (eski, yeni) in (KARAR_28_45.get(('places', p.get('NE_ID')), {}) if kahin
                                else {}).items():
            assert k[a] == eski, (p.get('NE_ID'), a, k[a], eski)
            k[a] = yeni
        yerler.append((round(float(lon), 5), round(float(lat), 5), k['name'], k['name_en'],
                       k['name_tr'], _say(p.get('MIN_ZOOM')), _say(p.get('LABELRANK')),
                       _ad(p.get('FEATURECLA')), k['adm0']))
    ulkeler = []
    for p in ham_ne['country_labels']:
        k = {a: _ad(p.get(n)) for a, n in _NE_AD.items()}
        for a, (eski, yeni) in (KARAR_28_45.get(('country_labels', p.get('ADM0_A3')), {})
                                if kahin else {}).items():
            assert k[a] == eski, (p.get('ADM0_A3'), a, k[a], eski)
            k[a] = yeni
        ulkeler.append((round(float(p['LABEL_X']), 5), round(float(p['LABEL_Y']), 5),
                        k['name'], k['name_en'], k['name_tr'], _say(p.get('MIN_LABEL')),
                        _say(p.get('MAX_LABEL')), _say(p.get('LABELRANK')),
                        k['adm0']))
    return {'places.json': yerler, 'country_labels.json': ulkeler}


def _satirlar(varlik: dict) -> list:
    return [tuple(r) for r in varlik['rows']]


def test_nicemle_en_yakin_1e5_basamaga_yuvarlar():
    """Ş3 (d), denetim D1: nicemleme kesme değil en yakına yuvarlama.
    Kâhin: tasarım §3.2, 1e-5° nicemleme -> hata en çok 0,5e-5°."""
    degerler = [-180.0 + i * 0.0360017 for i in range(10001)]
    degerler += [0.0000079, -0.0000079, 41.0123456, -80.6043449, 179.9999979]
    olcek = hat.KOORDINAT_OLCEGI
    assert olcek == 100_000
    # Sınavın gücü: kümede kesmenin yuvarlamadan ayrıldığı değerler var.
    assert sum(int(x * olcek) != round(x * olcek) for x in degerler) > 1000
    for x in degerler:
        assert abs(hat.nicemle(x) / olcek - x) <= 0.5e-5 + 1e-10, x


def test_gercek_koordinatlar_ham_ne_ile_1e5(ham_ne, gercek_uretim):
    """Ş3 (a), denetim D3: yer ve ülke etiketi konumları ham NE'nin 5 ondalığa
    yuvarlanmış değeriyle birebir (1e-5° ≈ 1,1 m; 2 ondalık ~1 km kayardı)."""
    from collections import Counter
    bek = _beklenen(ham_ne)
    for ad, sec in (('places.json', (0, 1, 7, 8)), ('country_labels.json', (0, 1, 8))):
        uretilen = Counter(tuple(r[i] for i in sec) for r in _satirlar(gercek_uretim[ad]))
        beklenen = Counter(tuple(r[i] for i in sec) for r in bek[ad])
        assert uretilen == beklenen, (ad, list((uretilen - beklenen).items())[:5])


def test_gercek_adlar_ham_ne_arti_karar_28_45(ham_ne, gercek_uretim):
    """§28-45: tablodaki satırlar yeni değerde, tablo dışındaki her ad ve alan
    ham NE ile aynı; künye düzeltmeyi dürüstçe beyan eder."""
    from collections import Counter
    bek = _beklenen(ham_ne)
    for ad in ('places.json', 'country_labels.json'):
        fark_u = Counter(_satirlar(gercek_uretim[ad])) - Counter(bek[ad])
        fark_b = Counter(bek[ad]) - Counter(_satirlar(gercek_uretim[ad]))
        assert not fark_u and not fark_b, (ad, list(fark_u)[:3], list(fark_b)[:3])
        prov = gercek_uretim[ad]['provenance']
        katman = ad.split('.')[0]
        beklenen_n = sum(1 for (k, _) in KARAR_28_45 if k == katman)
        assert prov['name_corrections']['not_applied'] == []
        assert len(prov['name_corrections']['applied']) == beklenen_n
        assert prov['name_corrections_applied'] == beklenen_n
        assert prov['source'].endswith('+ HRMA ad düzeltmeleri, karar §28-45')
        assert prov['source'].startswith('Natural Earth v5.1.2')
        for s in prov['name_corrections']['applied']:
            assert s['note'].strip()
            beklenen = KARAR_28_45[(katman, s['key'])]
            assert {c['field']: (c['old'], c['new']) for c in s['changes']} == beklenen
    # Değişmeyeceği adıyla yazılanlar ham değerinde.
    yer = {r[0:2]: r for r in _satirlar(gercek_uretim['places.json'])}
    for (katman, anahtar), alanlar in KARAR_28_45_DEGISMEZ.items():
        if katman == 'country_labels':
            satir = [r for r in _satirlar(gercek_uretim[katman + '.json']) if r[8] == anahtar]
        else:
            f = [f for f in ham_ne['places'] if f['properties'].get('NE_ID') == anahtar][0]
            satir = [yer[tuple(round(float(c), 5) for c in f['geometry']['coordinates'][:2])]]
        assert len(satir) == 1, (katman, anahtar)
        alan_sira = ['lon', 'lat', 'name', 'name_en', 'name_tr']
        for a, deger in alanlar.items():
            assert satir[0][alan_sira.index(a)] == deger, (katman, anahtar, a)
    # Sınavın gücü: kâhinsiz (ham) beklenti tablo satırları kadar ayrışır.
    ham = _beklenen(ham_ne, kahin=False)
    for ad in ('places.json', 'country_labels.json'):
        katman = ad.split('.')[0]
        n = sum(1 for (k, _) in KARAR_28_45 if k == katman)
        assert sum((Counter(bek[ad]) - Counter(ham[ad])).values()) == n


def test_ad_duzeltme_tablosu_karar_28_45_ile_ayni():
    tablo = {(d.katman, d.anahtar): {a: (e, y) for a, e, y in d.alanlar}
             for d in hat.AD_DUZELTMELERI}
    assert len(tablo) == len(hat.AD_DUZELTMELERI), 'tabloda tekrarlı anahtar'
    assert tablo == KARAR_28_45
    for d in hat.AD_DUZELTMELERI:
        assert d.kunye.strip() and d.adm0
    # Satırların doğrulandığı kaynak: v5.1.2 SHA256SUMS ile aynı dosya.
    if (GERCEK_KAYNAK / hat.SHA_LISTESI).is_file():
        liste = hat.sha_listesini_oku(GERCEK_KAYNAK)
        for dosya, sha in hat.AD_DUZELTMESI_KAYNAK_SHA.items():
            assert liste['%s/%s' % (hat.NE_ALT_DIZIN, dosya)] == sha, dosya


def test_depodaki_etiket_varliklari_ham_ne_arti_karar_28_45(ham_ne):
    """Commit'lenen places.json ve country_labels.json = ham NE + §28-45."""
    from collections import Counter
    if not (VARLIK_DIZIN / 'places.json').is_file():
        pytest.skip('hrma/static/map yok')
    bek = _beklenen(ham_ne)
    for ad in ('places.json', 'country_labels.json'):
        v = json.loads((VARLIK_DIZIN / ad).read_text(encoding='utf-8'))
        assert Counter(_satirlar(v)) == Counter(bek[ad]), ad
        assert v['provenance']['name_corrections']['not_applied'] == []


#: Yer satırlarının ülke kodu (ham NE ADM0_A3); ham kaynaksız bekçi için.
KARAR_28_45_YER_ADM0 = {1159127441: 'TUR', 1159144591: 'AZE', 1159134155: 'UKR',
                        1159134145: 'UKR', 1159140707: 'CHN', 1159126219: 'SYR',
                        1159126193: 'SYR', 1159136459: 'KGZ', 1159134335: 'UZB',
                        1159151263: 'ROU', 1159149403: 'ROU', 1159135835: 'ROU',
                        1159127789: 'ROU', 1159150561: 'UKR', 1159134151: 'UKR',
                        1159147519: 'UKR', 1159134141: 'UKR'}


def test_depodaki_etiket_varliklari_karar_28_45_ham_kaynaksiz():
    """Ham NE olmayan makinede de (CI) depodaki varlık §28-45'i taşır: her
    satırın ülkesinde eski değer HİÇ, yeni değer TAM BİR kez geçer (ölçüldü:
    eski değer düzeltmeden önce o ülkede tam bir kez geçiyordu)."""
    if not (VARLIK_DIZIN / 'places.json').is_file():
        pytest.skip('hrma/static/map yok')
    assert set(KARAR_28_45_YER_ADM0) == {k for (t, k) in KARAR_28_45 if t == 'places'}
    for ad, katman in (('places.json', 'places'), ('country_labels.json', 'country_labels')):
        v = json.loads((VARLIK_DIZIN / ad).read_text(encoding='utf-8'))
        f = v['fields']
        for (t, anahtar), alanlar in KARAR_28_45.items():
            if t != katman:
                continue
            adm0 = anahtar if t == 'country_labels' else KARAR_28_45_YER_ADM0[anahtar]
            ulkede = [r for r in v['rows'] if r[f.index('adm0')] == adm0]
            for alan, (eski, yeni) in alanlar.items():
                if alan == 'adm0':
                    continue        # ülke kodu ayrı bekçide (Kırım, ad ile)
                degerler = [r[f.index(alan)] for r in ulkede]
                assert degerler.count(eski) == 0, (ad, anahtar, alan, eski)
                assert degerler.count(yeni) == 1, (ad, anahtar, alan, yeni)


# --- Fail-closed (sentetik fixture) ----------------------------------------

def _kaynagi_yeniden_yaz(kok: pathlib.Path, dosya: str, ozellikler: list) -> None:
    ne = kok / hat.NE_ALT_DIZIN
    _yaz_geojson(ne / dosya, ozellikler)
    satirlar = ['%s  %s/%s' % (hashlib.sha256(y.read_bytes()).hexdigest(), hat.NE_ALT_DIZIN,
                               y.name) for y in sorted(ne.iterdir())]
    (kok / hat.SHA_LISTESI).write_text('\n'.join(satirlar) + '\n', encoding='utf-8')


def _ulke_ozelligi(**ek):
    p = dict(NAME='Turkey', NAME_EN='Turkey', NAME_TR='Türkiye', LABEL_X=34.5, LABEL_Y=39.0,
             MIN_LABEL=2, MAX_LABEL=7, LABELRANK=2, ADM0_A3='TUR')
    p.update(ek)
    return _ozellik({'type': 'Polygon',
                     'coordinates': [[[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 10.0]]]},
                    **p)


def _yer_ozelligi(**ek):
    p = dict(NAME='Elâzığ', NAME_EN='Elazığ', NAME_TR='Elâzığ', MIN_ZOOM=6, LABELRANK=8,
             FEATURECLA='Admin-1 capital', ADM0_A3='TUR', POP_MAX=1, NE_ID=1159127441)
    p.update(ek)
    return _ozellik({'type': 'Point', 'coordinates': [39.22, 38.67]}, **p)


@pytest.mark.parametrize('dosya,ozellikler,desen', [
    # Eski değer ham NE ile tutmuyor (NE değişmiş).
    (hat.SINIR_GORUNUMU_DOSYALARI['varsayilan'], [_ulke_ozelligi(NAME_EN='Turkiye')],
     'NE değişmiş'),
    (hat.YERLER_DOSYASI, [_yer_ozelligi(NAME_TR='Elazığ')], 'NE değişmiş'),
    # Anahtar tutuyor ama ülke kodu değil.
    (hat.YERLER_DOSYASI, [_yer_ozelligi(ADM0_A3='XXX')], 'NE değişmiş'),
    # Kararlı anahtar iki kayda uyuyor.
    (hat.YERLER_DOSYASI, [_yer_ozelligi(), _yer_ozelligi()], 'birden çok kayda'),
])
def test_ad_duzeltmesi_kaniti_tutmazsa_uretim_durur(tmp_path, dosya, ozellikler, desen):
    kok = _sentetik_kaynak(tmp_path / 'k')
    _kaynagi_yeniden_yaz(kok, dosya, ozellikler)
    with pytest.raises(hat.KaynakHatasi, match=desen):
        hat.uret(kok, _sentetik_110m(tmp_path), butce=10 ** 9)


def test_ad_duzeltmesi_dogrulanan_kaynakta_eksik_satir_durur(tmp_path, monkeypatch):
    """Tablonun doğrulandığı dosyada (sha256 tutuyor) bulunamayan satır
    üretimi durdurur; başka kaynakta adıyla 'not_applied' beyan edilir."""
    kok = _sentetik_kaynak(tmp_path / 'k')
    dosyalar, _ = hat.uret(kok, _sentetik_110m(tmp_path), butce=10 ** 9)
    yer = json.loads(dosyalar['places.json'])['provenance']
    ulke = json.loads(dosyalar['country_labels.json'])['provenance']
    assert yer['name_corrections']['applied'] == []
    assert len(yer['name_corrections']['not_applied']) == sum(
        1 for (k, _) in KARAR_28_45 if k == 'places')
    assert '+' not in yer['source'], 'düzeltme uygulanmadığı halde kaynak satırı ek taşıyor'
    # Sentetik ülke kaydı TUR/'Turkey': satır uygulanır, künyede beyan edilir.
    assert [s['key'] for s in ulke['name_corrections']['applied']] == ['TUR']
    assert ulke['source'].endswith('+ HRMA ad düzeltmeleri, karar §28-45')
    sha = hashlib.sha256((kok / hat.NE_ALT_DIZIN / hat.YERLER_DOSYASI).read_bytes()).hexdigest()
    monkeypatch.setitem(hat.AD_DUZELTMESI_KAYNAK_SHA, hat.YERLER_DOSYASI, sha)
    with pytest.raises(hat.KaynakHatasi, match='kaynakta bulunamadı'):
        hat.uret(kok, _sentetik_110m(tmp_path), butce=10 ** 9)


# ---------------------------------------------------------------------------
# Kırım sınırı, karar §28-45/Kırım (14 Eki 2026): Perekop çizgisi düşülür
# ---------------------------------------------------------------------------
# Kâhin: karar metni ("NE varsayılan sınır çizgilerindeki Perekop 'Disputed
# (please verify)' Rusya⟷Ukrayna çizgisi (10m ve 50m; eski 110m katmanında
# varsa o da) künyeli düşülür") + görev metnindeki kutu. Kutu ve sınıf burada
# ayrıca yazılır; üreticinin sabitlerinden OKUNMAZ.

#: Perekop kıstağı kutusu (boylam en az, en çok, enlem en az, en çok).
KARAR_28_45_PEREKOP_KUTUSU = (33.3, 35.4, 45.6, 46.4)
KARAR_28_45_TARTISMALI = 'Disputed (please verify)'
KARAR_28_45_SINIR_DOSYALARI = {'10m': 'ne_10m_admin_0_boundary_lines_land.geojson',
                               '50m': 'ne_50m_admin_0_boundary_lines_land.geojson'}


def _perekop_kutusunda(lon: float, lat: float) -> bool:
    k = KARAR_28_45_PEREKOP_KUTUSU
    return k[0] <= lon <= k[1] and k[2] <= lat <= k[3]


def _depodaki_sinir_cizgileri() -> dict:
    """{basamak: [[(lon, lat), ...], ...]} depodaki HMV1 'borders' katmanı."""
    m = json.loads((VARLIK_DIZIN / 'vectors_manifest.json').read_text(encoding='utf-8'))
    sonuc = {}
    for basamak, b in m['levels'].items():
        okunan = hmv1_oku((VARLIK_DIZIN / b['file']).read_bytes(), b['layers'])
        sonuc[basamak] = [[(x / hat.KOORDINAT_OLCEGI, y / hat.KOORDINAT_OLCEGI) for x, y in c]
                          for c in okunan['borders']]
    return sonuc


def test_depodaki_sinir_katmanlarinda_perekop_cizgisi_yok_karar_28_45():
    """10m, 50m ve 110m 'borders' katmanlarında Perekop kutusunda hiçbir köşe
    kalmaz (ölçüldü: düzeltmeden önce kutuda yalnız Perekop çizgisinin
    köşeleri vardı: 10m 46, 50m 15, 110m 6). Manifest künyesi düşüşü söyler."""
    if not (VARLIK_DIZIN / 'vectors_manifest.json').is_file():
        pytest.skip('hrma/static/map yok')
    cizgiler = _depodaki_sinir_cizgileri()
    assert set(cizgiler) == {'110m', '50m', '10m'}
    for basamak, liste in cizgiler.items():
        assert liste, basamak
        kutuda = [p for c in liste for p in c if _perekop_kutusunda(*p)]
        assert kutuda == [], (basamak, kutuda[:3])
    m = json.loads((VARLIK_DIZIN / 'vectors_manifest.json').read_text(encoding='utf-8'))
    prov = m['provenance']
    assert "karar §28-45/Kırım" in prov['source']
    assert prov['boundary_corrections']['dropped_lines'] == {'50m/borders': 1, '10m/borders': 1}
    assert prov['boundary_corrections']['legacy_110m'] is True
    assert "Türkiye'nin resmî görüşü" in prov['boundary_corrections']['decision']
    for basamak in ('50m', '10m'):
        k = m['levels'][basamak]['layers']['borders']['boundary_corrections']
        assert [d['featurecla'] for d in k['dropped']] == [KARAR_28_45_TARTISMALI]
        assert [sorted(d['country_pair']) for d in k['dropped']] == [['RUS', 'UKR']]
        assert k['not_applied'] == []
    assert m['levels']['110m']['source']['boundary_corrections']['point_count_after'] == \
        json.loads(hat.ESKI_110M.read_text(encoding='utf-8'))['point_count']


def test_eski_110m_yedeginde_perekop_cizgisi_yok_karar_28_45():
    """Eski 110m yedek katmanı (ürün vektör varlığı yokken bunu çizer):
    'borders' içinde Perekop kutusunda köşe yok; point_count tutarlı."""
    veri = json.loads(hat.ESKI_110M.read_text(encoding='utf-8'))
    kutuda = []
    for i, duz in enumerate(veri['layers']['borders']):
        for j in range(0, len(duz) - 1, 2):
            if _perekop_kutusunda(duz[j], duz[j + 1]):
                kutuda.append((i, duz[j], duz[j + 1]))
    assert kutuda == [], kutuda[:3]
    assert veri['point_count'] == sum(len(d) // 2 for L in veri['layers'].values() for d in L)


@gercek_kaynak
def test_gercek_sinirlar_ham_ne_eksi_perekop_karar_28_45():
    """Üretilen 10m ve 50m 'borders' kesim kümesi = ham NE kesim kümesi eksi
    Perekop kaydı. Başka hiçbir çizgi değişmez. Perekop kaydı kâhinle seçilir:
    FEATURECLA tartışmalı ve bütün köşeleri kutuda (10m'de ülke çifti RUS/UKR)."""
    dosyalar, _ = hat.uret(GERCEK_KAYNAK, butce=10 ** 9)
    m = json.loads(dosyalar['vectors_manifest.json'])
    q = hat.nicemle
    for basamak, dosya in KARAR_28_45_SINIR_DOSYALARI.items():
        ham = json.loads((GERCEK_KAYNAK / hat.NE_ALT_DIZIN / dosya).read_text(encoding='utf-8'))
        kalan, dusen = [], []
        for f in ham['features']:
            if not f.get('geometry'):
                continue
            p = f['properties']
            cizgiler = list(hat.cizgileri_ayikla(f['geometry']))
            koseler = [k for c in cizgiler for k in c]
            perekop = (p.get('FEATURECLA') == KARAR_28_45_TARTISMALI
                       and all(_perekop_kutusunda(k[0], k[1]) for k in koseler))
            (dusen if perekop else kalan).append((p, cizgiler))
        assert len(dusen) == 1, (basamak, len(dusen))
        if basamak == '10m':
            p = dusen[0][0]
            assert {p['ADM0_A3_L'], p['ADM0_A3_R']} == {'RUS', 'UKR'}
        beklenen = []
        for _, cizgiler in kalan:
            for c in cizgiler:
                n = [(q(k[0]), q(k[1])) for k in c]
                n = [x for j, x in enumerate(n) if j == 0 or x != n[j - 1]]
                if len(n) >= 2:
                    beklenen.extend(zip(n, n[1:]))
        okunan = hmv1_oku(dosyalar['vectors_%s.bin' % basamak],
                          m['levels'][basamak]['layers'])
        assert sorted(_kesimler(okunan['borders'])) == sorted(beklenen), basamak
        # Sınavın gücü: düşen kaydın kesimleri gerçekten ayrışıyor.
        assert len(dusen[0][1][0]) >= 6


def _sinir_kaydi(koordinatlar, **ek):
    p = dict(FEATURECLA='Disputed (please verify)', ADM0_A3_L='RUS', ADM0_A3_R='UKR',
             BRK_A3='B89', ne_id=1746708787, MIN_ZOOM=0)
    p.update(ek)
    return _ozellik({'type': 'LineString', 'coordinates': koordinatlar}, **p)


_PEREKOP_ORNEK = [[33.63, 46.12], [34.4, 46.0], [35.0, 45.73]]
_SINIR_10M = hat.BASAMAKLAR['10m']['borders']


@pytest.mark.parametrize('kayit,desen', [
    # NE kimliği tutmuyor (NE değişmiş).
    (_sinir_kaydi(_PEREKOP_ORNEK, ne_id=1), 'tabloya uymuyor'),
    # Tartışmalı RUS/UKR çizgisi kutu dışına taşıyor.
    (_sinir_kaydi(_PEREKOP_ORNEK + [[36.5, 46.0]]), 'tabloya uymuyor'),
    # Kutuda başka sınıf bir çizgi.
    (_sinir_kaydi(_PEREKOP_ORNEK, FEATURECLA='International boundary (verify)'),
     'tabloya uymuyor'),
    # Kutuda başka ülke çifti.
    (_sinir_kaydi(_PEREKOP_ORNEK, ADM0_A3_L='GEO'), 'tabloya uymuyor'),
])
def test_sinir_duzeltmesi_kaniti_tutmazsa_uretim_durur(tmp_path, kayit, desen):
    kok = _sentetik_kaynak(tmp_path / 'k')
    _kaynagi_yeniden_yaz(kok, _SINIR_10M, [kayit])
    with pytest.raises(hat.KaynakHatasi, match=desen):
        hat.uret(kok, _sentetik_110m(tmp_path), butce=10 ** 9)


def test_sinir_duzeltmesi_uygulanir_ve_kunyeye_yazilir(tmp_path):
    kok = _sentetik_kaynak(tmp_path / 'k')
    diger = _ozellik({'type': 'LineString', 'coordinates': [[30.0, 40.0], [31.0, 41.0]]},
                     FEATURECLA='International boundary (verify)', ne_id=5)
    _kaynagi_yeniden_yaz(kok, _SINIR_10M, [_sinir_kaydi(_PEREKOP_ORNEK), diger])
    dosyalar, _ = hat.uret(kok, _sentetik_110m(tmp_path), butce=10 ** 9)
    m = json.loads(dosyalar['vectors_manifest.json'])
    k = m['levels']['10m']['layers']['borders']['boundary_corrections']
    assert [d['ne_id'] for d in k['dropped']] == [1746708787]
    okunan = hmv1_oku(dosyalar['vectors_10m.bin'], m['levels']['10m']['layers'])
    assert okunan['borders'] == [[(3000000, 4000000), (3100000, 4100000)]]
    assert m['provenance']['source'].endswith('+ HRMA sınır düzeltmesi, karar §28-45/Kırım')
    # 50m'de aday yok ve kaynak doğrulanan dosya değil: adıyla beyan.
    k50 = m['levels']['50m']['layers']['borders']['boundary_corrections']
    assert k50['dropped'] == [] and len(k50['not_applied']) == 1


def test_sinir_duzeltmesi_dogrulanan_kaynakta_eslesme_yoksa_hicbir_dosya_yazilmaz(
        tmp_path, monkeypatch):
    kok = _sentetik_kaynak(tmp_path / 'k')
    sha = hashlib.sha256((kok / hat.NE_ALT_DIZIN / _SINIR_10M).read_bytes()).hexdigest()
    monkeypatch.setitem(hat.SINIR_DUZELTMESI_KAYNAK_SHA, _SINIR_10M, sha)
    cikti = tmp_path / 'cikti'
    # 110m: depodaki (düzeltilmiş) yedek katman; yalnız 10m satırı eksik.
    rc = hat.main(['--kaynak', str(kok), '--cikti', str(cikti)])
    assert rc == 3
    assert not cikti.exists() or list(cikti.iterdir()) == []


def test_eski_110m_perekop_cizgisi_kalirsa_uretim_durur(tmp_path):
    kok = _sentetik_kaynak(tmp_path / 'k')
    yol = tmp_path / 'earth_borders.json'
    yol.write_text(json.dumps({
        'source': 'test', 'license': 'test', 'retrieved_utc': 'test', 'format': 'test',
        'point_count': 8,
        'layers': {'borders': [[0.0, 0.0, 1.0, 1.0],
                               [33.44, 45.97, 33.7, 46.22, 34.41, 46.01]],
                   'coastline': [[-170.0, 5.0, -100.0, 5.0]]}}), encoding='utf-8')
    with pytest.raises(hat.KaynakHatasi, match='Perekop'):
        hat.uret(kok, yol, butce=10 ** 9)


# ---------------------------------------------------------------------------
# Kırım yerleşimleri, karar §28-45/Kırım: adm0 RUS -> UKR
# ---------------------------------------------------------------------------
#: Kırım kutusu (görev metni): boylam 32,4-36,7, enlem 44,3-46,25.
KARAR_28_45_KIRIM_KUTUSU = (32.4, 36.7, 44.3, 46.25)
#: Görev metnindeki altı yerleşim (ham NE NAME).
KARAR_28_45_KIRIM_YERLERI = {'Sevastopol', 'Simferopol', 'Kerch', 'Yevpatoriya', 'Yalta',
                             'Dzhankoy'}


def _kirimda(lon, lat):
    k = KARAR_28_45_KIRIM_KUTUSU
    return k[0] <= lon <= k[1] and k[2] <= lat <= k[3]


def test_depodaki_kirim_yerlesimleri_adm0_ukr_karar_28_45():
    """Ham kaynaksız (CI): Kırım kutusundaki her yerleşim UKR, RUS hiç yok;
    görev metnindeki altı ad kutuda tam bir kez."""
    if not (VARLIK_DIZIN / 'places.json').is_file():
        pytest.skip('hrma/static/map yok')
    v = json.loads((VARLIK_DIZIN / 'places.json').read_text(encoding='utf-8'))
    f = v['fields']
    kutuda = [r for r in v['rows'] if _kirimda(r[f.index('lon')], r[f.index('lat')])]
    assert sorted(r[f.index('name')] for r in kutuda) == sorted(KARAR_28_45_KIRIM_YERLERI)
    assert {r[f.index('adm0')] for r in kutuda} == {'UKR'}
    kirim_kunye = [s for s in v['provenance']['name_corrections']['applied']
                   if any(c['field'] == 'adm0' for c in s['changes'])]
    assert len(kirim_kunye) == 6
    for s in kirim_kunye:
        assert "karar §28-45/Kırım" in s['note']
        assert [c for c in s['changes'] if c['field'] == 'adm0'] == [
            {'field': 'adm0', 'old': 'RUS', 'new': 'UKR'}]


@gercek_kaynak
def test_kirim_kutusu_ham_ne_ile_olculur_karar_28_45(ham_ne):
    """Ham NE'de kutudaki yerleşimlerin hepsi RUS ve görev metnindeki altı ad."""
    kutuda = [f['properties'] for f in ham_ne['places']
              if _kirimda(*f['geometry']['coordinates'][:2])]
    assert sorted(p['NAME'] for p in kutuda) == sorted(KARAR_28_45_KIRIM_YERLERI)
    assert {p['ADM0_A3'] for p in kutuda} == {'RUS'}
    kahin = {k for (t, k), a in KARAR_28_45.items() if t == 'places' and 'adm0' in a}
    assert {p['NE_ID'] for p in kutuda} == kahin


def test_kirim_kutusunda_tabloda_olmayan_rus_yerlesimi_uretimi_durdurur(tmp_path,
                                                                        monkeypatch):
    kok = _sentetik_kaynak(tmp_path / 'k')
    satir = [d for d in hat.AD_DUZELTMELERI if d.anahtar == 1159134141]
    monkeypatch.setattr(hat, 'AD_DUZELTMELERI', tuple(satir))
    dzhankoy = _ozellik({'type': 'Point', 'coordinates': [34.4, 45.717]}, NAME='Dzhankoy',
                      NAME_EN='Dzhankoi', NAME_TR='Canköy', MIN_ZOOM=7, LABELRANK=8,
                      FEATURECLA='Populated place', ADM0_A3='RUS', POP_MAX=1,
                      NE_ID=1159134141)
    fazla = _ozellik({'type': 'Point', 'coordinates': [35.0, 45.0]}, NAME='X', NAME_EN='X',
                     NAME_TR='X', MIN_ZOOM=7, LABELRANK=8, FEATURECLA='Populated place',
                     ADM0_A3='RUS', POP_MAX=1, NE_ID=99)
    _kaynagi_yeniden_yaz(kok, hat.YERLER_DOSYASI, [dzhankoy])
    sha = hashlib.sha256((kok / hat.NE_ALT_DIZIN / hat.YERLER_DOSYASI).read_bytes()).hexdigest()
    monkeypatch.setitem(hat.AD_DUZELTMESI_KAYNAK_SHA, hat.YERLER_DOSYASI, sha)
    dosyalar, _ = hat.uret(kok, _sentetik_110m(tmp_path), butce=10 ** 9)
    yer = json.loads(dosyalar['places.json'])
    assert [r[-1] for r in yer['rows']] == ['UKR']
    _kaynagi_yeniden_yaz(kok, hat.YERLER_DOSYASI, [dzhankoy, fazla])
    sha = hashlib.sha256((kok / hat.NE_ALT_DIZIN / hat.YERLER_DOSYASI).read_bytes()).hexdigest()
    monkeypatch.setitem(hat.AD_DUZELTMESI_KAYNAK_SHA, hat.YERLER_DOSYASI, sha)
    with pytest.raises(hat.KaynakHatasi, match='Kırım kutusundaki'):
        hat.uret(kok, _sentetik_110m(tmp_path), butce=10 ** 9)
