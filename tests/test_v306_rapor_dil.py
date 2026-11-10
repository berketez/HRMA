"""V306/RAPOR-DİL bekçileri — Türkçe arayüzden indirilen PDF raporun dili.

ÖLÇÜLEN KUSUR (RAPOR-HATA §5, taban 686c34b98; bu kulvarın ``once/``
ölçümü): TR arayüzden inen PDF tamamen İngilizceydi (istekte dil alanı yok,
üretici sabit İngilizce basıyordu); Helvetica (WinAnsi) ğ ş ı İ Ğ Ş
harflerini taşımıyordu; TR'de sayılar noktalı ondalıkla basılıyordu; tehlike
bloğunda alan adlarının alt çizgisiz hâli ve küçük harf sınıf adları
basılıyordu.

D1  İstek dili: ``lang`` {en, tr}; liste dışı değer adıyla 422; alan yoksa
    'en' (beyanlı varsayılan).
D2  Yazı tipi: DejaVu Sans ailesi; bulunamazsa adlı hata (sessiz Helvetica
    yok).
D3  Sayı biçimi: TR'de virgüllü ondalık, binlik ayracı yok; sayı değişmez.
D4  Rapor sözlüğü (i18n_report.js): biçim, EN/TR paritesi, ekranla çakışma
    yok (aynı İngilizceye iki Türkçe yok).

Kanıt: docs/scofield/raw/OH/V306/rapor-dil/RAPOR.md.
"""
import io
import pathlib
import re

import pytest

from hrma.export import rapor_sozluk as rs
from hrma.export import pdf_generator as pg

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
RAPOR_JS = JS / 'i18n_report.js'

MOTOR = {'motor_name': 'RD-T1', 'motor_type': 'solid',
         'chamber_pressure': 69.0, 'propellant_mass': 1.63,
         'chamber_diameter': 60.2, 'chamber_length': 518.5,
         'throat_diameter': 12.49, 'exit_diameter': 40.34}
SONUC = {'performance': {'thrust': 1257.9, 'specific_impulse': 133.0,
                         'burn_time': 1.9, 'total_impulse': 2125.6}}


def _pdf_metni(veri):
    pypdf = pytest.importorskip('pypdf')
    okuyucu = pypdf.PdfReader(io.BytesIO(veri))
    return ' '.join(' '.join((s.extract_text() or '').split())
                    for s in okuyucu.pages)


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


# ---------------------------------------------------------------------------
# D1 — istek dili
# ---------------------------------------------------------------------------
def _istek(istemci, govde, tur='summary'):
    return istemci.post('/api/export-pdf/' + tur, json=govde)


def test_dil_alani_yoksa_ingilizce(istemci):
    r = _istek(istemci, {'motor_data': MOTOR, 'analysis_results': SONUC})
    assert r.status_code == 200
    metin = _pdf_metni(r.data)
    assert 'Motor Configuration' in metin
    assert 'Motor Yapılandırması' not in metin


def test_tr_istegi_turkce_belge(istemci):
    r = _istek(istemci, {'motor_data': MOTOR, 'analysis_results': SONUC,
                         'lang': 'tr'})
    assert r.status_code == 200
    metin = _pdf_metni(r.data)
    assert 'Analiz Sonuçları' in metin
    assert 'Analysis Results' not in metin


@pytest.mark.parametrize('deger', ['de', 'TR', 'english', 7, ['tr'], True])
def test_liste_disi_dil_adiyla_422(istemci, deger):
    r = _istek(istemci, {'motor_data': MOTOR, 'analysis_results': SONUC,
                         'lang': deger})
    assert r.status_code == 422
    govde = r.get_json()
    alanlar = [a['field'] for a in govde['invalid_fields']]
    assert alanlar == ['lang']
    assert govde['invalid_fields'][0]['accepted_values'] == ['en', 'tr']


def test_dort_indirme_noktasi_dili_gonderir():
    """solid/liquid exportPDF, advanced exportAnalysisPDF, app.js exportReport."""
    yerler = (('hrma/templates/solid.html', 'const requestData = {'),
              ('hrma/templates/liquid.html', 'const requestData = {'),
              ('hrma/templates/advanced.html',
               'async function exportAnalysisPDF('),
              ('hrma/static/js/app.js', "fetch('/api/export-pdf/summary'"))
    for yol, capa in yerler:
        kaynak = (KOK / yol).read_text(encoding='utf-8')
        i = kaynak.index(capa)
        pencere = kaynak[i:i + 2500]
        assert re.search(r'\blang: \(typeof window !== .undefined. && '
                         r'window\.I18N\) \? window\.I18N\.lang : undefined,',
                         pencere), yol


# ---------------------------------------------------------------------------
# D2 — yazı tipi
# ---------------------------------------------------------------------------
def test_yazi_tipi_dejavu_ve_turkce_harf_glifi():
    from reportlab.pdfbase import pdfmetrics
    pg.rapor_yazi_tiplerini_kaydet()
    for ad, _dosya in pg.RAPOR_YAZI_TIPI_DOSYALARI:
        yazi = pdfmetrics.getFont(ad)
        cmap = yazi.face.charToGlyph
        for harf in 'ğşıİĞŞçöüÇÖÜ⋅→≥θØ':
            assert ord(harf) in cmap, (ad, harf)
    g = pg.PDFReportGenerator(lang='tr')
    for stil in g.styles.byName.values():
        assert not str(getattr(stil, 'fontName', '')).startswith(
            ('Helvetica', 'Times')), stil.name


def test_yazi_tipi_yoksa_adli_hata(monkeypatch, tmp_path):
    monkeypatch.setattr(pg, '_YAZI_TIPI_KAYITLI', [])
    monkeypatch.setattr(pg, 'rapor_yazi_tipi_dizini', lambda: str(tmp_path))
    with pytest.raises(pg.RaporYaziTipiYok) as hata:
        pg.PDFReportGenerator(lang='tr')
    assert 'DejaVuSans.ttf' in str(hata.value)


# ---------------------------------------------------------------------------
# D3 — sayı biçimi
# ---------------------------------------------------------------------------
def test_fmt_tr_virgul_en_nokta_sayi_ayni():
    for dil, beklenen in (('en', '1257.9'), ('tr', '1257,9')):
        with rs.dil_baglami(dil):
            assert pg.PDFReportGenerator._fmt(1257.94) == beklenen
            assert pg.PDFReportGenerator._fmt(None) == 'N/A'
            assert pg.PDFReportGenerator._fmt(12.5, '{:.1f}%') == (
                '12.5%' if dil == 'en' else '%12,5')
            # binlik ayracı yok (ekranın I18N.number kuralı)
            assert ',' not in pg.PDFReportGenerator._fmt(123456.0, '{:.0f}')


# ---------------------------------------------------------------------------
# D4 — rapor sözlüğü
# ---------------------------------------------------------------------------
def _blok(dil):
    kaynak = RAPOR_JS.read_text(encoding='utf-8')
    m = re.search(r'^\s{8}%s:\s*\{' % dil, kaynak, re.M)
    assert m
    govde = kaynak[m.end():]
    son = govde.index('\n        }')
    return dict(re.findall(r"^\s*'([^']+)':\s*'((?:[^'\\]|\\.)*)',?$",
                           govde[:son], re.M))


def test_rapor_sozlugu_parite_ve_onek():
    en, tr = _blok('en'), _blok('tr')
    assert en and set(en) == set(tr)
    assert all(k.startswith('report.') for k in en)
    assert rs.RAPOR_SOZLUK_DOSYASI in rs.RAPOR_SOZLUK_PARCALARI
    assert rs.RAPOR_SOZLUK_PARCALARI[-1] == 'i18n_report.js'


def test_rapor_sozlugu_ekranla_cakismaz():
    """Ekranda karşılığı olan İngilizce, rapor sözlüğünde BAŞKA bir Türkçeyle
    yazılamaz (aynı İngilizceye iki Türkçe yok). Büyük/küçük harf duyarsız:
    rapor 'Annular gap t' yazsaydı ekranın 'Annular Gap t' karşılığını
    gölgelerdi (ters arama önce birebir bakar). Ekranla AYNI Türkçeyi taşıyan
    kayıt (sınıf adının okunur biçimi gibi) çakışma sayılmaz."""
    en, tr = _blok('en'), _blok('tr')
    rapor = {rs.normalize(rs._kacis_coz(v)).casefold():
             rs.normalize(rs._kacis_coz(tr[k])).casefold()
             for k, v in en.items()}
    ekran = {}
    for ad in rs.RAPOR_SOZLUK_PARCALARI[:-1]:
        kaynak = (JS / ad).read_text(encoding='utf-8')
        e_govde = dict(rs._CIFT.findall(rs._blok(kaynak, 'en') or ''))
        t_govde = dict(rs._CIFT.findall(rs._blok(kaynak, 'tr') or ''))
        for k, v in e_govde.items():
            if k in t_govde:
                ekran.setdefault(rs.normalize(rs._kacis_coz(v)).casefold(),
                                 set()).add(rs.normalize(
                                     rs._kacis_coz(t_govde[k])).casefold())
    cakisan = sorted(e for e, t in rapor.items()
                     if e in ekran and t not in ekran[e])
    assert not cakisan, cakisan[:20]


def test_rapor_sozlugunde_ayni_ingilizce_tek_turkce():
    en, tr = _blok('en'), _blok('tr')
    gorulen = {}
    for k, v in en.items():
        assert gorulen.setdefault(rs.normalize(v), tr[k]) == tr[k], v


# ---------------------------------------------------------------------------
# D5 — kalem 7: belge metni bekçisi (tur vakalarının GERÇEK gövdeleriyle)
# ---------------------------------------------------------------------------
VAKA = KOK / 'docs/scofield/raw/OH/V306/muhendis-turu'
TIP = {'hibrit': 'hybrid', 'kati': 'solid', 'sivi': 'liquid'}

#: Belgenin KASITLI olarak andığı makine adları (künye): çözücü alanının
#: adı okuyucunun yanıtta bulacağı yerdir ('Values below are read from this
#: design's own solver fields (cooling_system, …)'), form alanı adı
#: ('max_wall_temp') ve simge adları. Bunlar çevrilmez; listesi kapalıdır.
KUNYE_ADLARI = {'cooling_system', 'thermal_protection', 'structural_analysis',
                'injection_system', 'max_wall_temp', 'cf_anchor', 'eta_c',
                'n_effective', 'motor_geometry', 'chamber_wall_zones',
                'two_phase_loss', 'analysis_results', 'motor_data',
                'total_impulse'}


def _vaka_govdesi(sistem, L):
    import json
    from tests.support.kanit import kanit_gerekli
    yol = kanit_gerekli(VAKA / sistem / 'vakalar' / (L + '.json'))
    d = json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))
    res = [r for r in d['istekler']
           if r['uc'] == '/api/flight-vehicle'][-1]['govde']['results']
    md = dict(res.get('motor') or {}) if sistem == 'hibrit' else {}
    md.update({'motor_name': 'BEKCI-' + L, 'motor_type': TIP[sistem]})
    if sistem == 'kati':
        for ad in ('chamber_pressure', 'propellant_mass', 'burn_time',
                   'specific_impulse', 'total_impulse'):
            if res.get(ad) is not None:
                md[ad] = res[ad]
        if res.get('max_thrust') is not None:
            md['thrust'] = res['max_thrust']
    return {'motor_data': md, 'analysis_results': res, 'charts': []}


@pytest.fixture(scope='module')
def belgeler(istemci):
    """Üç motor türünün L1 vakası: TR ve EN 'complete' belge + çevrilemeyen
    parça kaydı (TR)."""
    import contextlib
    sonuc = {}
    # Uyarı cümlelerini EKRANIN sözlüğü kurar (rapor_sozluk.uyari_cumlesi);
    # içlerindeki çözücü değerleri ('outside_anchor_envelope_unverified') ve
    # ekran metnindeki adlar bu kulvarın değil, ekran/sunucu sözlüğünündür
    # (DEVİR) — kayda alınır, ham ad bekçisi bunları ayırır.
    asil = rs.uyari_cumlesi
    for sistem in ('hibrit', 'kati', 'sivi'):
        govde = _vaka_govdesi(sistem, 'L1')
        for dil in ('en', 'tr'):
            uyarilar = []

            def _kayitli(kayit, d='en', _u=uyarilar):
                cumle = asil(kayit, d)
                if cumle:
                    _u.append(cumle)
                return cumle
            rs.uyari_cumlesi = _kayitli
            try:
                with rs.cevrilmeyen_kaydi() as kayit, \
                        rs.desen_kaydi() as desenler, \
                        contextlib.redirect_stdout(io.StringIO()):
                    r = istemci.post('/api/export-pdf/complete',
                                     json=dict(govde, lang=dil))
            finally:
                rs.uyari_cumlesi = asil
            assert r.status_code == 200, (sistem, dil, r.data[:300])
            sonuc[(sistem, dil)] = (_pdf_metni(r.data),
                                    list(kayit) + uyarilar + desenler)
    return sonuc


def _sozluk_cumleleri():
    """Sözlükte TR karşılığı olan (ve karşılığı İngilizceden FARKLI) en az
    dört sözcüklü, yer tutucusuz İngilizce cümleler."""
    en, tr = rs.sozluk('en'), rs.sozluk('tr')
    cumleler = set()
    for k, v in en.items():
        t = tr.get(k)
        if t is None or k.startswith(rs.PARCA_ONEKI):
            continue
        v_n, t_n = rs.normalize(v), rs.normalize(t)
        if v_n == t_n or '{' in v_n or '<' in v_n or '$' in v_n:
            continue
        if len(v_n.split()) >= 4:
            cumleler.add(v_n)
    return cumleler


@pytest.mark.parametrize('sistem', ['hibrit', 'kati', 'sivi'])
def test_tr_belgede_sozlukte_karsiligi_olan_ingilizce_kalmaz(belgeler, sistem):
    metin, kayit = belgeler[(sistem, 'tr')]
    # Çevrilemeyen ÇÖZÜCÜ cümleleri (DEVİR DİL-SUNUCU) çıkarılır: içlerinde
    # geçen bir ad (ör. itici adı) belgenin kendi metni değildir.
    for parca in sorted(set(kayit), key=len, reverse=True):
        metin = metin.replace(rs.normalize(parca), ' ')
    kalan = sorted(c for c in _sozluk_cumleleri() if c in metin)
    assert not kalan, kalan[:10]


@pytest.mark.parametrize('sistem', ['hibrit', 'kati', 'sivi'])
def test_tr_belgede_ham_anahtar_ve_alan_adi_kalmaz(belgeler, sistem):
    metin, kayit = belgeler[(sistem, 'tr')]
    # Sözlük/uyarı kodu (warn.* / report.* / panel.*) hiç basılmaz.
    assert not re.search(r'\b(?:warn|report|panel|liq|solid|adv)\.[a-z_]+\.',
                         metin)
    # Alt çizgili ad: yalnız çevrilemeyen ÇÖZÜCÜ cümlelerinin içinde (DEVİR
    # DİL-SUNUCU) ya da künye adı olarak kalabilir; belgenin kendi etiket ve
    # değerlerinde kalmaz.
    cozucu = ' '.join(kayit)
    adlar = set(re.findall(r'(?<![\w.])([a-z][a-z0-9]*(?:_[a-z0-9]+)+)(?![\w])',
                           metin))
    kalan = sorted(a for a in adlar
                   if a not in KUNYE_ADLARI and a not in cozucu
                   and not re.fullmatch(r'[a-z]_[a-z0-9]+', a))  # p_e simgesi
    assert not kalan, kalan


@pytest.mark.parametrize('sistem', ['hibrit', 'kati', 'sivi'])
def test_tr_belgede_turkce_harfler_metin_katmanindan_cikar(belgeler, sistem):
    metin, _kayit = belgeler[(sistem, 'tr')]
    for harf in 'ğşıİçöü':
        assert harf in metin, harf
    for sozcuk in ('Motor Yapılandırması', 'Başvurulan kaynaklar',
                   'Analiz Sonuçları', 'Teknik Ek'):
        assert sozcuk in metin, sozcuk


@pytest.mark.parametrize('sistem', ['hibrit', 'kati', 'sivi'])
def test_tr_belgede_ondalik_virgul(belgeler, sistem):
    """Performans tablosunun sayıları TR'de virgüllü (sayının kendisi aynı)."""
    tr_metin, _ = belgeler[(sistem, 'tr')]
    en_metin, _ = belgeler[(sistem, 'en')]
    en_sayi = re.findall(r'Specific Impulse (\d+)\.(\d) s', en_metin)
    tr_sayi = re.findall(r'Özgül itki (\d+),(\d) s', tr_metin)
    assert en_sayi and en_sayi == tr_sayi


@pytest.mark.parametrize('sistem', ['hibrit', 'kati', 'sivi'])
def test_en_belge_ingilizce_kalir(belgeler, sistem):
    metin, _ = belgeler[(sistem, 'en')]
    assert not rs._TR_HARFI.search(metin.replace('BEKCI', ''))
    for baslik in ('Motor Configuration', 'Analysis Results',
                   'Technical Appendix', 'Solver Warnings'):
        assert baslik in metin
