# -*- coding: utf-8 -*-
"""ÖH Dalga-28 / kulvar bekci-cevirisi, aşama 1 — bekçiler.

Kapsanan defter kalemi:

* **OH-D27-17** [orta] Panel süpürmesinin KENDİ KÖRLÜĞÜ.
  ``tests/test_d15_ui_paneller_a1.py`` içindeki ``_gorunur`` ölçütü, bir
  yaprağın "ekranda görünür" sayılması için ekranın HERHANGİ bir sayı
  jetonunun — kendi basamak sayısıyla yuvarlandığında — yaprağa eşit
  olmasını yetiyordu. Ölçüt AD içermediği için sayı çakışmasına açıktı ve
  süpürme kendi kör noktasını sayamıyordu.

  ÖLÇÜLDÜ (``docs/scofield/raw/OH/D28/bekci-cevirisi/a1/``; aynı render
  dökümü, yalnız ölçüt değişti — ürün kodu dokunulmadı): 297 yaprak,
  kör sayısı **6 → 10**. Çakışmayla aklanan dördü:

  =========================================== ============ ==============
  yaprak                                      değer        aklayan jeton
  =========================================== ============ ==============
  ``blast_distances.lethal.scaled_..._kg13``  2,7494       "3" (risk satırı
                                                           ``#3 Pressure``)
  ``blast_distances.serious_injury.scaled_``  4,5400       "/ 5" ölçek üstü
  ``pressure_safety.inner_diameter_mm``       100,0 mm     "100.0 kPa"
                                                           aşırı basıncı
  ``pressure_safety.wall_thickness_mm``       5,0 mm       "5.000 kg" yakıt
                                                           kütlesi + "/ 5"
  =========================================== ============ ==============

  Son ikisi BÜYÜKLÜK bile tutmuyordu: bir BASINÇ bir ÇAPI, bir KÜTLE bir
  CİDAR KALINLIĞINI aklıyordu. Onarım ölçütü ad+değer düzeyine çekti; bu
  dosya ölçütün çakışmayı bir daha kabul etmeyeceğini bağlar.

Yöntem: ürün kodu çalıştırılmaz; ölçütün kendisi SENTETİK ekranlarla
sınanır (node/uç gerekmez). Gerçek render süpürmesi kendi dosyasında
(``test_d15_ui_paneller_a1.py``) koşar.
"""

import ast
import importlib.util
import pathlib
import re

import pytest

TESTS = pathlib.Path(__file__).resolve().parent


def _yukle(ad, dosya):
    spec = importlib.util.spec_from_file_location(ad, TESTS / dosya)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


UI = _yukle('_d28_ui_a1', 'test_d15_ui_paneller_a1.py')


def _satir(alan, deger, etiket=None):
    return ('<tr><td style="p"><strong><span data-safety-field="' + alan
            + '" style="s">' + (etiket or alan) + '</span></strong></td>'
            + '<td style="p">' + deger + '</td></tr>')


def _kutu(etiket, deger):
    return ('<div style="letter-spacing:0.08em;">' + etiket + '</div>\n'
            '<div style="font-size:1.25rem;">' + deger + '</div>')


#: fix-26b'nin ölçtüğü ekranın küçültülmüş ama YAPI OLARAK aynı hâli:
#: patlama satırı (makine yollu), risk ölçeği (insan etiketli, "/ 5"
#: taşıyan), basınç kutusu ve serbest cümle.
EKRAN_HTML = (
    '<h4>safety_analysis.explosive_hazards</h4>'
    '<table style="t">' + _satir('blast_distances.lethal', '3.5 m @ 100.0 kPa')
    + '</table>'
    '<h4>Individual Risks (1 = lowest, 5 = highest)</h4>'
    '<table style="t"><tr><td style="p"><strong>Pressure</strong></td>'
    '<td style="p">3.0 / 5</td></tr>'
    '<tr><td style="p"><strong>Structural</strong></td>'
    '<td style="p">1.0 / 5</td></tr></table>'
    '<h4>Mitigation Priority</h4>'
    '<table style="t"><thead><tr><th style="p">Priority</th>'
    '<th style="p">Risk Area</th><th style="p">Score</th></tr></thead>'
    '<tbody><tr><td style="p"><strong>#3</strong></td>'
    '<td style="p">Pressure</td><td style="p">2.0 / 5</td></tr></tbody>'
    '</table>'
    '<h4>Pressure Vessel Summary</h4>' + _kutu('Design', '60.0 bar')
    + '<p>propellant_mass_kg 5.000 kg</p>')


def _ekran(html=None):
    h = EKRAN_HTML if html is None else html
    return UI._ekran_bolgeleri(
        {'html': h, 'text': UI._duz_metin(h)})


@pytest.fixture(scope='module')
def ekran():
    return _ekran()


class TestOlcutAdDegerDuzeyinde:
    """OH-D27-17: süpürme ölçütü sayı çakışmasını görünür saymaz."""

    #: (yol, değer, çakışan jetonu taşıyan bölge) — ölçülen dört vaka.
    CAKISMALAR = [
        ('explosive_hazards.blast_distances.lethal.'
         'scaled_distance_m_per_kg13', 2.7494332277460307, '#3 sirasi'),
        ('explosive_hazards.blast_distances.serious_injury.'
         'scaled_distance_m_per_kg13', 4.540048389354556, '1.0 / 5'),
        ('pressure_safety.inner_diameter_mm', 100.0, '100.0 kPa'),
        ('pressure_safety.wall_thickness_mm', 5.0, '5.000 kg'),
    ]

    @pytest.mark.parametrize('yol,deger,tasiyan', CAKISMALAR)
    def test_baska_alanin_jetonu_yapragi_aklamaz(self, ekran, yol, deger,
                                                 tasiyan):
        """Ölçülen dört çakışma: jeton ekranda VAR, ama başka alanın."""
        eski = any(round(deger, d) == t
                   for t, d in UI._ekran_jetonlari(ekran['metin']))
        assert eski, ('ölçüm tabanı çürüdü: sentetik ekran artık ' + yol
                      + ' ile çakışan jetonu (' + tasiyan + ') taşımıyor, '
                      'yani eski ölçütün kusuru gösterilemez')
        assert UI._gorunur(yol, deger, ekran) is False, (
            yol + ' ekranda KENDİ ADIYLA yok; onu yalnız ' + tasiyan
            + ' bölgesindeki yabancı jeton akladı — ölçüt yine ad+değer '
              'düzeyinin altına düştü')

    def test_kendi_satirindaki_deger_gorunur(self, ekran):
        """Ölçüt sıkılaşırken MEŞRU görünürlük düşmez (makine yolu bağı)."""
        assert UI._gorunur(
            'explosive_hazards.blast_distances.lethal.distance_m',
            3.4999, ekran) is True
        assert UI._gorunur(
            'explosive_hazards.blast_distances.lethal.overpressure_kpa',
            100.0, ekran) is True

    def test_insan_etiketli_kutu_yapragi_adlar(self, ekran):
        """``Design`` kutusu ``design_pressure_bar``ı adlar (sözcük bağı)."""
        assert UI._gorunur('pressure_safety.design_pressure_bar', 60.0,
                           ekran) is True
        assert UI._gorunur('risk_assessment.individual_risks.structural',
                           1.0, ekran) is True

    def test_etiketsiz_serbest_metin_bolge_sayilmaz(self, ekran):
        """Cümlede/başlıkta duran SAYI, komşu alanı aklayamaz.

        Ölçüldü: "adın 140 karakter yakınında ara" gevşemesi gerçek
        ekranda tek yaprağı bile aklamıyor, buna karşılık bölüm
        başlığındaki ``5 = highest`` jetonunu komşu alanın değeri
        yapabiliyordu. Kapı ölçümle kapatıldı.
        """
        assert UI._gorunur('inputs_used.propellant_mass_kg', 5.0,
                           ekran) is False, (
            'etiketsiz cümledeki 5.000 kg, adı geçse bile bölge değildir')
        satirli = _ekran(EKRAN_HTML + '<table style="t">'
                         + _satir('inputs_used.propellant_mass_kg',
                                  '5.000 kg') + '</table>')
        assert UI._gorunur('inputs_used.propellant_mass_kg', 5.0,
                           satirli) is True, (
            'ölçüt sıkılaşırken kendi satırındaki değer de düştü')

    def test_her_yerde_gecen_sozcuk_bag_kurmaz(self):
        """``safety`` gibi her bölümü etiketleyen sözcük ADLAMAZ — ÖLÇÜLÜR."""
        html = ''.join(
            '<h4>safety_analysis.blok%d</h4><table style="t">' % i
            + _satir('blok%d.alan' % i, '%d.0' % (i + 1)) + '</table>'
            for i in range(6))
        e = _ekran(html)
        assert 'safety' in e['genel'], (
            'ölçüm tabanı çürüdü: her bölümde geçen sözcük genel sayılmıyor')
        assert UI._gorunur('pressure_safety.safety', 3.0, e) is False, (
            'her bölüm başlığındaki `safety` sözcüğü yaprağı akladı')

    def test_metin_yapragi_tum_ekranda_aranir(self, ekran):
        """Ölçülen çakışma SAYIDA idi; cümle ölçütü daralmadı."""
        assert UI._gorunur('pressure_safety.vessel_status', 'MEDIUM PRESSURE',
                           _ekran(EKRAN_HTML + '<p>MEDIUM PRESSURE</p>')
                           ) is True
        assert UI._gorunur('x.y', 'boyle bir cumle ekranda yok',
                           ekran) is False


class TestGuvenlikYaprakBorcuSimetrisi:
    """fix-26b'nin sözü: borç DÖRT patlama kaydının TAMAMIDIR.

    Hüküm SİMETRİ üstünedir, "hep borçlu" üstünde değil. Dört kayıt
    (``lethal``, ``serious_injury``, ``minor_injury``,
    ``property_damage``) panelde AYNI okuyucudan (``addBlastRow``) geçer;
    ikisi ekranda öbürü değil diye bir hâl OLAMAZ. Dolayısıyla sekiz
    yolun ya SEKİZİ de envanterde olur (okuyucu künyeyi hiç almıyor) ya
    da HİÇBİRİ (borç ödendi). Arada bir sayı görülüyorsa ya süpürme kör
    (OH-D27-17'nin ta kendisi: tabanda 6/8 vardı) ya da envanter
    bayatlamıştır. Bu biçim, arayuz kulvarının borcu ÖDEMESİNİ de
    engellemez: sekizi birden düştüğünde bekçi yeşil kalır.
    """

    #: Simetriye tabi sekiz yol — panelin tek okuyucusundan geçerler.
    YOLLAR = frozenset(
        'explosive_hazards.blast_distances.%s.%s' % (k, alan)
        for k in ('lethal', 'serious_injury', 'minor_injury',
                  'property_damage')
        for alan in ('basis', 'scaled_distance_m_per_kg13'))

    def test_dort_kayit_ya_hep_ya_hic(self):
        assert set(UI.BLAST_KAYITLARI) == {
            'lethal', 'serious_injury', 'minor_injury', 'property_damage'}, (
            'ölçüm tabanı çürüdü: patlama kayıtları listesi değişmiş')
        kayitli = self.YOLLAR & set(UI.GUVENLIK_YAPRAK_BORCU)
        assert kayitli in (frozenset(), self.YOLLAR), (
            'patlama künyesi borcu KISMİ: dört kayıt aynı okuyucudan '
            'geçer, ikisi kör öbürü değil olamaz. Ya süpürme kör kaldı '
            '(OH-D27-17) ya envanter bayat. Kayıtlı: '
            + repr(sorted(kayitli)) + ' — eksik: '
            + repr(sorted(self.YOLLAR - kayitli)))

    def test_borc_gerekcesi_dalgayi_adlar(self):
        """Anonim af yok: her satır KAYNAK dalgayı yazar (D26 şart değil)."""
        anonim = [y for y, neden in UI.GUVENLIK_YAPRAK_BORCU.items()
                  if not re.search(r'\bD\d{1,2}\b', str(neden))]
        assert not anonim, anonim

    def test_kural_dalga_kodu_ister_ama_anonimi_reddeder(self):
        """Gevşetme YÖNLÜ: 'D26' çakması kalktı, anonimlik kalmadı."""
        kaynak = (TESTS / 'test_d15_ui_paneller_a1.py').read_text(
            encoding='utf-8')
        # AST ile ayıkla: metin dilimlemesi komşu imlere (``@xfail``)
        # bağımlıydı, o im silinince bekçi ÇÖKERDİ. Gövde artık
        # işlevin kendi kaynağıdır.
        govde = None
        for d in ast.walk(ast.parse(kaynak)):
            if isinstance(d, ast.FunctionDef) and \
                    d.name == 'test_yaprak_borcu_olu_satir_tasimaz':
                govde = ast.get_source_segment(kaynak, d)
        assert govde, ('ölçüm tabanı çürüdü: '
                       'test_yaprak_borcu_olu_satir_tasimaz artık yok')
        assert "'D26' not in str(neden)" not in govde, (
            'borç gerekçesi yine yalnız D26 kabul ediyor — D26\'dan ESKİ '
            'kusurlar envantere giremez')
        assert re.search(r'D\\\\d\{1,2\}', govde) or \
            r'\bD\d{1,2}\b' in govde, (
            'gerekçe kuralı dalga kodu aramıyor: anonim satır geçebilir')
        assert 'not str(neden).strip()' in govde, (
            'boş gerekçe denetimi düştü')


# ---------------------------------------------------------------------------
# OH-D27-17 notunun ikinci yarısı: "aynı desen diğer süpürmelerde taranır".
#
# Desenin imzası şudur: bir SAYI, ADI denetlenmeden, BELGE düzeyindeki bir
# metin havuzunda aranıyor. Tarama ``docs/scofield/raw/OH/D28/
# bekci-cevirisi/a1/desen_taramasi.py`` ile ölçüldü; ölçüm burada BEKÇİYE
# çevriliyor, yoksa rapor bayatlar.
#
# ÖLÇÜLDÜ (once_desen.json / sonra_desen.json, 599 test dosyası):
#   sınıf A (jeton yuvarlama)  taban 1  ->  şimdi 2
#   sınıf C (süpürme içinde adsız arama) 5 -> 5, SAYI arayan 0 -> 0
#
# Sınıf A'nın tabandaki TEK yeri ``_gorunur``dı — yani HÜKMÜN kendisi ad
# denetimsiz sayı eşleşmesine dayanıyordu; kusur buydu. Bugünkü iki yeri
# de meşrudur: biri ölçütün DEĞER katmanı (adı çağıran denetler), öbürü bu
# dosyanın ölçüm tabanı denetimi. Sınıf C'nin beş yerinin beşi de METİN
# arar (etiket, rota yolu, kural metni, izin listesi anahtarı); ölçülen
# çakışma SAYIDAYDI, uzun metinde rastlantısal eşleşme ölçülmedi.
# ---------------------------------------------------------------------------

#: Jeton basamağıyla yuvarlama (``round(v, <değişken>)``) yapmasına izin
#: verilen YERLER — (dosya, kapsayan işlev). Liste TEK YÖNLÜ değil ÇİFT
#: yönlüdür: yeni bir yer doğarsa da, buradaki bir yer ölürse de kırmızı
#: yanar (envanter "unutulmuş af listesi"ne dönüşemez).
JETON_YUVARLAMA_MESRU = {
    # V3.0.5 T-ÇAPA-C1: iki yer de basamağı ÜRÜNÜN beyanından alır, basılan
    # jetondan değil (OH-D27-17'nin kusuru jetonun kendi basamağıydı).
    ('tests/test_d22_arayuz_a1.py', 'test_ilk_cagrida_son_deger_basilir'):
        'V3.0.5 T-ÇAPA-C1 (ÖH D28 ölçütü, OH-D27-17; düğüm ÖH D22 arayuz '
        'a1) — basamak kartın data-decimals beyanından '
        '(kanıt harness kaydında ``ondalik``); karşılaştırma basılan dizgeyle '
        'TAM eşitliktir (toFixed biçimi).',
    ('tests/test_unit_contract.py',
     'test_solid_case_diameter_matches_case_design'):
        'V3.0.5 T-ÇAPA-C1 (ÖH D28 ölçütü, OH-D27-17) — basamak ürünün '
        'adlı sabitinden '
        '(``ENG_HEADER_DECIMALS[\'diameter_mm\']``, çizim başlığının '
        'yayımladığı basamak), basılan jetondan değil.',
    ('tests/test_d15_ui_paneller_a1.py', '_deger_bolgede'):
        'ÖH D28 / OH-D27-17 — ölçütün DEĞER katmanı. Yuvarlama burada '
        'kalabilir çünkü havuz artık TÜM ekran değil, yaprağı ADLAYAN tek '
        'bölgedir; adı ``_bolge_bagli`` denetler.',
    ('tests/test_d28_bekci_cevirisi_a1.py',
     'test_baska_alanin_jetonu_yapragi_aklamaz'):
        'ÖH D28 / OH-D27-17 — ESKİ ölçütün kusurunu gösteren ölçüm tabanı '
        'denetimi: sentetik ekranda çakışan jetonun HÂLÂ durduğunu kanıtlar.',
}

#: Süpürme içinde adsız SAYI araması: sıfır. Tavan değil TAM SAYIDIR —
#: OH-D27-17 deseninin ta kendisi budur, muafiyeti yoktur.
SUPURME_ADSIZ_SAYI_TAVANI = 0

#: Sınıf C'nin ölçülen METİN aramaları. SAYIM DEĞİL KÜME (D27 dersi 11):
#: yeni bir yer doğarsa adıyla girer, sayı yükseltilmez. Altısı da METİN
#: arar — uzun ve ayırt edici bir dizgenin rastlantıyla eşleşmesi
#: ölçülmedi; ölçülen çakışma SAYIDAYDI.
SUPURME_ADSIZ_METIN_YERLERI = {
    ('tests/test_cfd_panel.py', 'test_olculen_sure_cuzdani_ekranda'):
        'ÖH D28 / OH-D27-17 taraması — aranan şey KİP ADI (dizge), sayı '
        'değil; ayrıca cfd kulvarının sahası.',
    ('tests/test_d23_altyapi_a1.py',
     'test_kapsam_sayfasi_olculemeyeni_temiz_gostermez'):
        'ÖH D28 / OH-D27-17 taraması — aranan şey ROTA YOLU '
        '(``/calculate_solid`` gibi), sayı değil.',
    ('tests/test_d26_arayuz_a4.py',
     'test_kural_muhru_bugunku_sablonda_duruyor'):
        'ÖH D28 / OH-D27-17 taraması — aranan şey ŞABLON KURALI (uzun '
        'kaynak parçası), sayı değil.',
    ('tests/test_no_fabricated_text_specs.py', 'scan_source'):
        'ÖH D28 / OH-D27-17 taraması — bu bir EKRAN araması bile değil: '
        'izin listesi (``ALLOWED_TEXT_SPECS``) üyeliği sınanıyor.',
    ('tests/test_safety_panel_defaults.py',
     'test_etiketler_kosum_karti_alan_listesinden'):
        'ÖH D28 / OH-D27-17 taraması — aranan şey İNSAN ETİKETİ; üstelik '
        'hüküm etiketin VARLIĞI üstünedir, bir yaprağın değeri üstünde '
        'değil.',
    ('tests/test_d37_hibrit_a1.py',
     'test_cwu6_acilir_pencere_ana_pencere_yokken_bildirim'):
        'ÖH V3 taban-b (14 Eki 2026; yer D37 hibrit a1\'de doğdu) — '
        'aranan şey SABİT bir cümle '
        '(\'The main HRMA window is closed\'), döngü değeri değil; '
        'sol işlenen AST\'de dizge sabiti. Tarayıcı döngü adı ``s``yi '
        'sabitin içinde ALT DİZE olarak buldu. Sayı aranmıyor.',
}

_DESEN_SUPURME = ('yapraklar', '_leaves', 'leaves', 'sayisal', 'alanlar',
                  'items')
_DESEN_BELGE = ('html', 'metin', 'text', 'ekran', 'govde', 'sayfa', 'icerik')
_DESEN_DAR = ('satir', 'cumle', 'hucre', 'note', 'kutu', 'blok')


def _sayi_arayan(ifade):
    return any(k in ifade for k in ('round(', ':.', 'float(', 'str(',
                                    '%d', '%f'))


class _DesenGezgini(ast.NodeVisitor):
    """Sınıf A ve sınıf C yerlerini toplar (desen_taramasi.py ile aynı)."""

    def __init__(self, yol):
        self.yol = yol
        self.yigin = []
        self.a = []
        self.c = []

    def _islev(self):
        return self.yigin[-1] if self.yigin else '(modül)'

    def visit_FunctionDef(self, d):
        self.yigin.append(d.name)
        self.generic_visit(d)
        self.yigin.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, d):
        ad = getattr(d.func, 'attr', None) or getattr(d.func, 'id', None)
        if ad == 'round' and len(d.args) == 2 and \
                not isinstance(d.args[1], ast.Constant):
            self.a.append((self.yol, self._islev(), d.lineno))
        self.generic_visit(d)

    def _dongu(self, hedef, iter_ifade, govde):
        if not any(k in ast.unparse(iter_ifade) for k in _DESEN_SUPURME):
            return
        adlar = {n.id for n in ast.walk(hedef) if isinstance(n, ast.Name)}
        for g in govde:
            for n in ast.walk(g):
                if not (isinstance(n, ast.Compare) and n.ops
                        and isinstance(n.ops[0], ast.In)):
                    continue
                sol = ast.unparse(n.left)
                sag = ast.unparse(n.comparators[0]).lower()
                if any(k in sag for k in _DESEN_DAR):
                    continue
                if not any(k in sag for k in _DESEN_BELGE):
                    continue
                if not any(a in sol for a in adlar):
                    continue
                self.c.append((self.yol, self._islev(), n.lineno,
                               _sayi_arayan(sol)))

    def visit_For(self, d):
        self._dongu(d.target, d.iter, d.body)
        self.generic_visit(d)

    def visit_comprehension(self, d):
        self._dongu(d.target, d.iter, [ast.Expr(value=i) for i in d.ifs])
        self.generic_visit(d)


@pytest.fixture(scope='module')
def desen():
    a, c = [], []
    for p in sorted(TESTS.rglob('*.py')):
        try:
            agac = ast.parse(p.read_text(encoding='utf-8'))
        except (SyntaxError, UnicodeDecodeError):
            continue
        g = _DesenGezgini('tests/' + p.relative_to(TESTS).as_posix())
        g.visit(agac)
        a.extend(g.a)
        c.extend(g.c)
    return {'a': a, 'c': c}


class TestDesenBaskaSupurmelerdeYok:
    """OH-D27-17'nin ikinci yarısı: desen depo genelinde taranır."""

    def test_jeton_yuvarlama_yalniz_mesru_yerlerde(self, desen):
        """Ekran jetonunun basamağıyla yuvarlama nerede yaşayabilir?"""
        yerler = {(d, i) for d, i, _s in desen['a']}
        yeni = sorted(yerler - set(JETON_YUVARLAMA_MESRU))
        assert not yeni, (
            'yeni bir süpürme ekran jetonunu KENDİ basamağıyla yuvarlıyor; '
            'ad denetimi olmadan bu OH-D27-17 kusurudur (sayı çakışması '
            'yaprağı aklar): ' + repr(yeni))
        olu = sorted(set(JETON_YUVARLAMA_MESRU) - yerler)
        assert not olu, (
            'muafiyet listesinde artık var olmayan yer duruyor — envanter '
            '"unutulmuş af listesi"ne dönüştü: ' + repr(olu))

    def test_supurme_icinde_adsiz_sayi_aramasi_yok(self, desen):
        """Süpürme döngüsü içinde ADSIZ sayı araması: ölçülen sayı 0."""
        sayi = sorted((d, i, s) for d, i, s, saydir in desen['c'] if saydir)
        assert len(sayi) <= SUPURME_ADSIZ_SAYI_TAVANI, (
            'bir süpürme, yaprağın SAYISINI belge düzeyinde adsız arıyor — '
            'OH-D27-17 deseni: ' + repr(sayi))

    def test_metin_aramalari_adiyla_kayitli(self, desen):
        """Sınıf C metin aramaları KÜME olarak kayıtlı (sayım değil)."""
        metin = {(d, i) for d, i, _s, saydir in desen['c'] if not saydir}
        yeni = sorted(metin - set(SUPURME_ADSIZ_METIN_YERLERI))
        assert not yeni, (
            'bir süpürme, döngü değerini belge düzeyinde adsız arıyor; '
            'aradığı SAYI ise OH-D27-17 kusurudur, METİN ise gerekçesiyle '
            'listeye adıyla girer: ' + repr(yeni))
        # Ölü satır: dosya duruyorsa işlev de durmalı. Dosya tümden
        # silinmişse (başka kulvarın işi) satır sessizce düşer.
        olu = sorted(y for y in set(SUPURME_ADSIZ_METIN_YERLERI) - metin
                     if (TESTS.parent / y[0]).exists())
        assert not olu, (
            'tarama envanterinde artık var olmayan yer duruyor — envanter '
            'bayatladı, satırı adıyla kaldır: ' + repr(olu))

    def test_gerekceler_dalgayi_adlar(self):
        """Muafiyetin her satırı KAYNAK dalgayı yazar (anonim af yok)."""
        kayit = dict(JETON_YUVARLAMA_MESRU)
        kayit.update(SUPURME_ADSIZ_METIN_YERLERI)
        anonim = [y for y, neden in kayit.items()
                  if not re.search(r'\bD\d{1,2}\b', str(neden))]
        assert not anonim, anonim
