"""ÖH Z5S / P10-Z5S-B — ``hrma.utils`` yardımcı katmanının bekçileri.

BAĞLANAN DEFTER KALEMLERİ
=========================
P10B1-01 (yüksek)  /api/find-optimum-of tek yanıtta iki O/F: ölçülen 6,8452
                   ⟷ "NASA/industry standard" bildirimi 7,50.
P10B1-02 (orta)    ``get_recommendation`` ``motor_type``ı hiç okumuyor —
                   hibrit, sıvı, katı ve uydurma ``'ZURAFA'`` için BİT-AYNI
                   cümle.
P10B1-03 (orta)    ``find_optimum_liquid`` bandı 1,0-5,0'te sabit; 12 çiftin
                   4'ünde "optimum" tam bant KENARI 5,0000 ve dönen sözlük
                   ``theoretical_optimum`` ile çelişiyor.
P10B1-04 (orta)    "Optimizer" arama yapmıyor, kendi tablo sabitini geri
                   okuyor; ``chamber_pressure`` optimumun yerini SIFIR kadar
                   değiştiriyor.
P10B1-15 (orta)    ``create_mixture`` boyutça tutarsız karışım kuralı: ``a``
                   katsayısının boyutu ``n``e bağlıyken dört farklı boyuttaki
                   ``a`` kütle payıyla toplanıyor.
P10B1-16 (orta)    Chug alt eşiğinin (0,15) DÖRDÜNCÜ kopyası ve bu kopya ürün
                   akışında CANLI (``/calculate_liquid`` ΔP kapısı).
P10B1-17 (orta)    ``calculate_total_impulse_auto`` bool deliği: ``thrust=True``
                   sayı sanılıyor, 10 s yanma için 10,0 N*s üretiliyor.
P10B1-18 (orta)    ``generate_motor_file({})`` boş girdiden TAM bir OpenRocket
                   ``.eng`` dosyası basıyor (1000 N / 10 s, 5 kg / 10 kg).

SAYILAR NEREDEN GELİYOR — EŞİĞİ-KENDİNDEN-TÜRETME YASAĞI
========================================================
Aşağıdaki DAVRANIŞ sayılarının hiçbiri üründen ithal edilmez; hepsi
28 Ağustos 2026 koşumunun çıktısıdır
(``docs/scofield/raw/OH/Z5S/p10b/olcum_once.json``):

    get_recommendation('hybrid'|'liquid'|'solid'|'ZURAFA'|'', 'n2o','htpb')
        -> beşinin beşi de "Recommended O/F ratio for HTPB/N2O: 7.50
           (NASA/industry standard)"                      [P10B1-02]
    /api/find-optimum-of  hybrid n2o/htpb Pc=20
        -> optimum_of_ratio 6,845236859025728
           recommendation   "... 7.50 (NASA/industry standard)"   [P10B1-01]
    find_optimum_liquid: n2o/htpb 5,0000 ⟷ tablo 7,50;
        n2o/paraffin 5,0000 ⟷ 8,00; ap/htpb 5,0000 ⟷ 6,00;
        ap/pban 5,0000 ⟷ 5,50                                     [P10B1-03]
    find_optimum_hybrid: Pc 1 bar ⟷ 1000 bar farkı 0,000000 (4 çiftte)
        tabloya uzaklık 0,0102/0,0408/0,0469/0,0714 < ızgara/2 = 0,112245
                                                                  [P10B1-04]
    create_mixture({'htpb':0.5,'paraffin':0.5}) -> a=7,690e-05;
        aynı karışım G_ox 1000x birimde 8,792e-05 (+%14,34)       [P10B1-15]
    validate_pressure_consistency: (110,100) RET / (120,100) GEÇ /
        (48,40) GEÇ                                               [P10B1-16]
    calculate_total_impulse_auto(True, 10, None) -> 10,0 N*s      [P10B1-17]
    generate_motor_file({}) -> "100.0 300.0 0 5.000 10.000 HRMA"  [P10B1-18]

Tek istisna P10B1-16'nın TEK-KAYNAK iddiasıdır: orada sayı değil NESNE
KİMLİĞİ sınanır (``is``), yani iddia eşiğin değerinden değil, kopyanın
varlığından türer.
"""

import ast
import io
import re
import tokenize

import pytest

from hrma.analysis import acoustic_modes
from hrma.utils import common_fixes as cf
from hrma.utils import optimum_of_ratio as oor
from hrma.utils.input_guard import InputError

KAYNAK_OOR = open(oor.__file__, encoding='utf-8').read()
KAYNAK_CF = open(cf.__file__, encoding='utf-8').read()


def _kod_govdesi(kaynak: str) -> str:
    """Belge-dizisi ve yorumlardan ARINDIRILMIŞ kaynak (yalnız KOD).

    Kaynak taraması yapan bekçiler KODU sınamalıdır. Bu depoda düzeltilen
    kusurun kendisi künyeye ALINTI olarak yazılır ("eski cümle şuydu: ...");
    ham metin taraması o alıntıyı ihlal sanar ve düzeltmeyi belgeleyen her
    yorumu yasaklamış olurdu. Satır düzeni korunur (satır numaraları kayar
    değil), yalnız içerik boşaltılır.
    """
    agac = ast.parse(kaynak)
    bosaltilacak = set()
    for dugum in ast.walk(agac):
        if not isinstance(dugum, (ast.Module, ast.FunctionDef,
                                  ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if ast.get_docstring(dugum, clean=False) is None:
            continue
        ilk = dugum.body[0]
        bosaltilacak.update(range(ilk.lineno, (ilk.end_lineno or
                                               ilk.lineno) + 1))

    satirlar = ['' if i in bosaltilacak else s
                for i, s in enumerate(kaynak.splitlines(), 1)]

    metin = '\n'.join(satirlar)
    for tok in tokenize.generate_tokens(io.StringIO(metin).readline):
        if tok.type != tokenize.COMMENT:
            continue
        satir_no, sutun = tok.start
        satirlar[satir_no - 1] = satirlar[satir_no - 1][:sutun]
    return '\n'.join(satirlar)


KOD_OOR = _kod_govdesi(KAYNAK_OOR)
KOD_CF = _kod_govdesi(KAYNAK_CF)


@pytest.fixture(scope='module')
def finder():
    return oor.OptimumOFRatioFinder()


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ===========================================================================
# P10B1-01 — tek yanıtta iki O/F
# ===========================================================================

#: Ölçülen denge taraması sonucu (28 Ağu 2026). İddia bu sayıya EŞİTLİK
#: dayatmaz (çözücü değişebilir); yalnız cümlenin BU sayıyı taşıdığını sınar.
OLCULEN_OPTIMUM = 6.845236859025728

#: Ölçülen tablo değeri — cümlenin ölçülen sayı YERİNE bunu basmadığı sınanır.
OLCULEN_TABLO = 7.5


class TestTekYanittaTekHukum:

    def test_dayanaksiz_NASA_atfi_kaynakta_YOK(self):
        """"(NASA/industry standard)" ibaresi modülden kalkmış olmalı.

        Deponun kendi kuralı: doğrulayamadığın atfı koyma
        (``acoustic_modes`` künye hükmü). Tablo sayıları DEĞİŞMEDİ.
        """
        assert 'NASA/industry standard' not in KOD_OOR, (
            'Dayanaksız kurum atfı geri gelmiş.')

    def test_oneri_cumlesi_OLCULEN_sayiyi_tasiyor(self, finder):
        cumle = finder.get_recommendation('hybrid', 'n2o', 'htpb',
                                          measured_of_ratio=OLCULEN_OPTIMUM)
        assert f'{OLCULEN_OPTIMUM:.2f}' in cumle, (
            f'Öneri cümlesi ölçülen sayıyı ({OLCULEN_OPTIMUM:.2f}) '
            f'taşımıyor: {cumle!r}')

    def test_oneri_cumlesi_tablo_sayisini_KUNYESIYLE_veriyor(self, finder):
        """İki sayı da görünür ama hangisinin ölçüldüğü belli olmalı."""
        cumle = finder.get_recommendation('hybrid', 'n2o', 'htpb',
                                          measured_of_ratio=OLCULEN_OPTIMUM)
        assert f'{OLCULEN_TABLO:.2f}' in cumle
        assert 'reference table' in cumle.lower()
        assert 'combustion equilibrium scan' in cumle.lower()

    def test_olculen_sayi_verilmezse_cumle_OPTIMUM_IDDIA_ETMEZ(self, finder):
        """Ölçüm yoksa tablo değeri "optimum" diye sunulamaz."""
        cumle = finder.get_recommendation('hybrid', 'n2o', 'htpb')
        assert 'not a computed optimum' in cumle.lower(), (
            f'Tablo değeri künyesiz "optimum" gibi sunuluyor: {cumle!r}')

    def test_ucta_referans_AYRI_kunyeli_alanda(self, client):
        r = client.post('/api/find-optimum-of',
                        json={'motor_type': 'hybrid', 'oxidizer': 'n2o',
                              'fuel': 'htpb', 'chamber_pressure': 20.0})
        assert r.status_code == 200
        g = r.get_json()
        ref = g.get('reference_optimum')
        assert isinstance(ref, dict), (
            'Referans tablo değeri ayrı künyeli alanda değil.')
        assert ref.get('is_equilibrium_search') is False
        assert 'reference' in str(ref.get('basis', '')).lower()
        assert g.get('optimum_of_ratio_basis')

    def test_ucun_iki_sayisi_ARTIK_CELISMIYOR(self, client):
        """Öneri cümlesi ile ``optimum_of_ratio`` alanı aynı hükmü anlatmalı.

        ÖLÇÜLEN KUSUR: cümle 7,50 diyordu, alan 6,845237 idi ve arayüz
        cümleyi BAŞARI mesajı olarak gösteriyordu.
        """
        r = client.post('/api/find-optimum-of',
                        json={'motor_type': 'hybrid', 'oxidizer': 'n2o',
                              'fuel': 'htpb', 'chamber_pressure': 20.0})
        g = r.get_json()
        olculen = float(g['optimum_of_ratio'])
        cumle = g['recommendation']
        assert f'{olculen:.2f}' in cumle, (
            f'Yanıttaki cümle ölçülen O/F ({olculen:.4f}) yerine başka bir '
            f'sayıyı sunuyor: {cumle!r}')
        assert 'NASA/industry standard' not in cumle


# ===========================================================================
# P10B1-02 — motor_type hükme girer
# ===========================================================================

class TestMotorTipiHukmeGirer:

    def test_taninmayan_tip_FAIL_CLOSED(self, finder):
        """Uydurma 'ZURAFA' artık cümle üretemez."""
        with pytest.raises(ValueError) as e:
            finder.get_recommendation('ZURAFA', 'n2o', 'htpb')
        assert 'motor_type' in str(e.value)
        assert 'ZURAFA' in str(e.value)

    def test_bos_tip_de_reddedilir(self, finder):
        with pytest.raises(ValueError):
            finder.get_recommendation('', 'n2o', 'htpb')

    def test_hibrit_ve_sivi_cumlesi_AYNI_DEGIL(self, finder):
        """Hibrit çift sıvı diye sorulursa cümle bunu SÖYLER.

        ÖLÇÜLEN KUSUR: beş farklı ``motor_type`` için bit-aynı dize.
        """
        hibrit = finder.get_recommendation('hybrid', 'n2o', 'htpb')
        sivi = finder.get_recommendation('liquid', 'n2o', 'htpb')
        assert hibrit != sivi, (
            'motor_type hâlâ hükme girmiyor: iki tip için bit-aynı cümle.')
        assert 'hybrid' in sivi.lower(), (
            f'Sınıf uyuşmazlığı beyan edilmiyor: {sivi!r}')

    def test_uc_tipin_ucu_de_ayri_hukum_veriyor(self, finder):
        cumleler = {tip: finder.get_recommendation(tip, 'n2o', 'htpb')
                    for tip in oor.SUPPORTED_MOTOR_TYPES}
        # Çift hibrit sınıfında: hibrit sorusu temiz, diğer ikisi uyarılı.
        assert len(set(cumleler.values())) >= 2
        assert 'NOTE' not in cumleler['hybrid']
        assert 'NOTE' in cumleler['liquid'] and 'NOTE' in cumleler['solid']

    def test_sinif_eslemesi_VERI_olarak_var(self):
        """Eşleme yorum satırı değil, okunabilir veri olmalı."""
        assert oor.PAIR_MOTOR_CLASS[('n2o', 'htpb')] == 'hybrid'
        assert oor.PAIR_MOTOR_CLASS[('lox', 'rp1')] == 'liquid'
        assert oor.PAIR_MOTOR_CLASS[('ap', 'pban')] == 'solid'
        # Tablodaki her çiftin bir sınıfı olmalı (sessiz boşluk yok).
        eksik = set(oor.OptimumOFRatioFinder().theoretical_optimums) - set(
            oor.PAIR_MOTOR_CLASS)
        assert not eksik, f'Sınıfı yazılmamış çiftler: {sorted(eksik)}'

    def test_motor_type_parametresi_govdede_OKUNUYOR(self):
        """Sahte bağımlılık yasağı: parametre ya kullanılır ya kaldırılır."""
        agac = ast.parse(KOD_OOR)
        govde = next(d for d in ast.walk(agac)
                     if isinstance(d, ast.FunctionDef)
                     and d.name == 'reference_optimum')
        adlar = {n.id for n in ast.walk(govde) if isinstance(n, ast.Name)}
        assert 'motor_type' in adlar, (
            'reference_optimum motor_type parametresini hâlâ okumuyor.')


# ===========================================================================
# P10B1-03 — tarama bandı referansı KAPSAR, kenar çözümü işaretlenir
# ===========================================================================

#: Eski sabit bandın ürettiği kenar değer (ölçüldü).
ESKI_BANT_KENARI = 5.0

#: Bandın kenarına düşen dört çift (ölçüldü) — düzeltmeden sonra
#: hiçbirinin kenarda kalmaması gerekir.
KENARDA_KALAN_CIFTLER = (('n2o', 'htpb'), ('n2o', 'paraffin'),
                         ('ap', 'htpb'), ('ap', 'pban'))

#: ÖH D16 / OH-Z5-17 — BEKÇİ ÇEVİRİSİ (gerekçeli, sessiz değil).
#:
#: Yukarıdaki dördün SON İKİSİ (``ap/htpb``, ``ap/pban``) KATI itici
#: çiftidir — modülün kendi ``PAIR_MOTOR_CLASS`` tablosu ikisine de
#: ``'solid'`` diyor. Bu iki çifti ``find_optimum_liquid``a sokan iddia,
#: SIVI dalın onlara bir sayı ÜRETMESİNİ şart koşuyordu; oysa çiftlerin
#: künyeli tepe Isp tablosunda (``peak_vac_isp``) karşılığı YOKTUR ve
#: sayı ancak ``_liquid_reference``ın sabit 320 s yedeğinden gelebilirdi.
#: Kardeş dal bunu zaten yapmıyor: ``find_optimum_hybrid`` aynı çiftlerde
#: fail-closed ``ValueError`` veriyor. Yani iddia, sıvı dalı kardeşinden
#: DAHA GEVŞEK tutan bir yedeği kilitliyordu.
#:
#: Band iddiaları bu yüzden sıvı dalın gerçekten hizmet ettiği çiftlerle
#: koşulur; katı çiftlerin fail-closed olduğu AYRI ve açık bir iddiaya
#: dönüştürüldü (aşağıda ``test_kati_cift_sivi_dalda_fail_closed``).
#: Kenar-değer regresyonu KAPSAM KAYBETMEZ: n2o/htpb ve n2o/paraffin
#: ölçümde kenarda kalan çiftlerin ikisidir ve hâlâ sınanıyor.
BANT_SIVI_CIFTLERI = tuple(
    cift for cift in KENARDA_KALAN_CIFTLER
    if oor.PAIR_MOTOR_CLASS.get(cift) != 'solid')

#: Aynı listedeki KATI çiftler — sıvı dalda sayı ÜRETİLMEMELİ.
BANT_KATI_CIFTLERI = tuple(
    cift for cift in KENARDA_KALAN_CIFTLER
    if oor.PAIR_MOTOR_CLASS.get(cift) == 'solid')


class TestSiviTaramaBandi:

    @pytest.mark.parametrize('ox,fu', BANT_KATI_CIFTLERI)
    def test_kati_cift_sivi_dalda_fail_closed(self, finder, ox, fu):
        """KATI çift sıvı taramasında sayı ALMAZ (kardeş dalla aynı kural).

        ÖH D16 / OH-Z5-17: eski hâlde ``_liquid_reference`` yalnız YAKITLA
        eşleşiyor, eşleşmezse sabit 320 s'ye düşüyordu; böylece katı çift
        için de "tepe Isp" üretiliyordu. ``find_optimum_hybrid`` aynı
        çiftte ``ValueError`` veriyor — iki dal artık aynı kuralda.
        """
        with pytest.raises(ValueError):
            finder.find_optimum_liquid(ox, fu)
        with pytest.raises(ValueError):
            finder.find_optimum_hybrid(ox, fu)

    @pytest.mark.parametrize('ox,fu', BANT_SIVI_CIFTLERI)
    def test_optimum_artik_bant_KENARINDA_degil(self, finder, ox, fu):
        d = finder.find_optimum_liquid(ox, fu)
        assert d['optimum_at_band_edge'] is False, (
            f'{ox}/{fu}: optimum hâlâ bandın kenarında '
            f"({d['optimum_of_ratio']:.4f}, band {d['scan_band']}).")
        assert abs(float(d['optimum_of_ratio']) - ESKI_BANT_KENARI) > 1e-9, (
            f'{ox}/{fu}: sonuç hâlâ eski sabit bandın kenar değeri '
            f'{ESKI_BANT_KENARI}.')

    @pytest.mark.parametrize('ox,fu', BANT_SIVI_CIFTLERI)
    def test_donen_sozluk_iki_CELISEN_sayi_tasimiyor(self, finder, ox, fu):
        """``optimum_of_ratio`` ile ``theoretical_optimum`` ayrışmamalı.

        ÖLÇÜLEN KUSUR: n2o/htpb için sözlük aynı anda 5,0000 ve 7,50
        taşıyordu (−%33,3).
        """
        d = finder.find_optimum_liquid(ox, fu)
        tablo = float(d['theoretical_optimum'])
        bulunan = float(d['optimum_of_ratio'])
        sapma = abs(bulunan - tablo) / tablo
        assert sapma < 0.05, (
            f'{ox}/{fu}: dönen sözlük çelişen iki sayı taşıyor — '
            f'optimum {bulunan:.4f} ⟷ tablo {tablo:.2f} (%{100 * sapma:.1f}).')

    def test_bant_referansi_ICINE_aliyor(self, finder):
        for ox, fu in BANT_SIVI_CIFTLERI + (('lox', 'rp1'), ('lox', 'lh2')):
            d = finder.find_optimum_liquid(ox, fu)
            alt, ust = d['scan_band']
            tepe = float(d['curve_peak_of_ratio'])
            assert alt < tepe < ust, (
                f'{ox}/{fu}: eğrinin tepesi ({tepe}) bandın '
                f'({alt}, {ust}) içinde değil.')

    def test_sabit_1_0_5_0_bandi_kaynakta_YOK(self):
        """Eski sabit band geri dönerse bekçi kırmızıya döner."""
        assert not re.search(r'linspace\(\s*1\.0\s*,\s*5\.0', KOD_OOR), (
            'Sabit 1,0-5,0 tarama bandı geri gelmiş.')

    def test_hibrit_dalinda_da_kenar_isareti_var(self, finder):
        d = finder.find_optimum_hybrid('n2o', 'htpb')
        assert d['optimum_at_band_edge'] is False
        assert 6.0 < float(d['optimum_of_ratio']) < 9.0


# ===========================================================================
# P10B1-04 — araç "tablo geri okuyucu" diye KÜNYELENİR
# ===========================================================================

#: Ölçülen: Pc 1 bar ⟷ 1000 bar arasında optimumun yeri 0,000000 kadar
#: değişiyor (dört hibrit çiftin dördünde de).
PC_KOR_CIFTLER = (('n2o', 'htpb'), ('n2o', 'paraffin'),
                  ('lox', 'htpb'), ('lox', 'paraffin'))


class TestTabloGeriOkumaKunyesi:

    @pytest.mark.parametrize('ox,fu', PC_KOR_CIFTLER)
    def test_beyan_OLCUMLE_uyusuyor(self, finder, ox, fu):
        """Künye "Pc optimumu etkilemez" diyorsa ölçüm de öyle demeli.

        Bu iddia iki yönlü çalışır: gerçek bir tarama bağlanırsa (Pc artık
        optimumu oynatırsa) beyan yalan olur ve bekçi KIRMIZI döner.
        """
        d1 = finder.find_optimum_hybrid(ox, fu, chamber_pressure=1.0)
        d2 = finder.find_optimum_hybrid(ox, fu, chamber_pressure=1000.0)
        fark = abs(float(d2['optimum_of_ratio'])
                   - float(d1['optimum_of_ratio']))
        beyan = d1['chamber_pressure_affects_optimum']
        assert beyan is (fark > 0), (
            f'{ox}/{fu}: künye "Pc etkiler={beyan}" diyor ama ölçülen fark '
            f'{fark:.6f}. Beyan ile davranış ayrışmış.')

    @pytest.mark.parametrize('ox,fu', PC_KOR_CIFTLER)
    def test_arac_DENGE_COZUCUSU_OLMADIGINI_soyluyor(self, finder, ox, fu):
        d = finder.find_optimum_hybrid(ox, fu)
        assert d['is_equilibrium_search'] is False
        assert 'not a searched optimum' in d['optimum_of_ratio_basis']

    @pytest.mark.parametrize('ox,fu', PC_KOR_CIFTLER)
    def test_sonuc_gercekten_tabloya_oturuyor(self, finder, ox, fu):
        """Künyenin ikinci yarısı: sonuç tablo değerinin ızgara komşusu.

        Beyan "tepe tabloya konur" diyor; ölçüm bunu doğrulamalı, yoksa
        künye de yanlış olurdu.
        """
        d = finder.find_optimum_hybrid(ox, fu)
        alt, ust = d['scan_band']
        izgara = (ust - alt) / (int(d['scan_points']) - 1)
        uzaklik = abs(float(d['optimum_of_ratio'])
                      - float(d['theoretical_optimum']))
        assert uzaklik <= izgara / 2 + 1e-9, (
            f'{ox}/{fu}: sonuç tabloya ızgara yarısından uzak '
            f'({uzaklik:.6f} > {izgara / 2:.6f}) — künye artık doğru değil.')

    def test_modul_basligi_CEA_iddiasini_tasimiyor(self):
        """Eski başlık "Uses NASA CEA data and real-time calculations" idi.

        İddia artık başlıkta ALINTI olarak geçebilir (künye onu çürütüyor);
        yasak olan, başlığın hâlâ o iddiayı SAHİPLENMESİdir. Bu yüzden
        başlığın açılış cümlesine bakılır, gövdesine değil.
        """
        baslik = ast.get_docstring(ast.parse(KAYNAK_OOR)) or ''
        acilis = [s for s in baslik.splitlines() if s.strip()][:3]
        assert not any('CEA' in s for s in acilis), (
            f'Başlık hâlâ CEA iddiasıyla açılıyor: {acilis}')
        assert 'DENGE ÇÖZÜCÜSÜ DEĞİLDİR' in baslik, (
            'Aracın ne OLMADIĞI başlıkta yazmıyor (P10B1-04 künyesi).')


# ===========================================================================
# P10B1-15 — boyutça tutarsız karışım kuralı
# ===========================================================================

class TestKarisimBoyutKapisi:

    def test_farkli_n_ile_karisim_REDDEDILIR(self):
        """ÖLÇÜLEN KUSUR: htpb+paraffin karışımı a=7,690e-05 üretiyordu."""
        mixer = cf.FuelMixtureSystem()
        with pytest.raises(ValueError) as e:
            mixer.create_mixture({'htpb': 0.5, 'paraffin': 0.5})
        metin = str(e.value)
        assert 'dimensionally inconsistent' in metin
        assert 'htpb' in metin and 'paraffin' in metin, (
            'Ret gerekçesi hangi bileşenlerin ayrıştığını söylemiyor.')

    def test_tum_ikili_karisimlar_reddedilir(self):
        """Tablodaki dört bileşenin n'leri farklı: hiçbir ikili geçemez."""
        mixer = cf.FuelMixtureSystem()
        adlar = sorted(mixer.base_fuels)
        for i, a in enumerate(adlar):
            for b in adlar[i + 1:]:
                with pytest.raises(ValueError):
                    mixer.create_mixture({a: 0.5, b: 0.5})

    def test_tek_bilesende_hukum_VERILIR(self):
        """Kapı kapalı-takılı değil: boyut sorunu yoksa sonuç üretilir."""
        mixer = cf.FuelMixtureSystem()
        m = mixer.create_mixture({'htpb': 1.0})
        assert m['a'] == pytest.approx(mixer.base_fuels['htpb']['a'])
        assert m['n'] == pytest.approx(mixer.base_fuels['htpb']['n'])
        assert m['density'] == pytest.approx(mixer.base_fuels['htpb']['density'])

    def test_ayni_n_li_bilesenler_toplanabiliyor(self, monkeypatch):
        """Boyut aynıysa kural uygulanır ve künye bunu SÖYLER."""
        mixer = cf.FuelMixtureSystem()
        taban = dict(mixer.base_fuels)
        taban['ikiz'] = {'density': 1000.0,
                         'a': taban['htpb']['a'] * 2,
                         'n': taban['htpb']['n']}
        monkeypatch.setattr(mixer, 'base_fuels', taban)
        m = mixer.create_mixture({'htpb': 0.5, 'ikiz': 0.5})
        assert m['n'] == pytest.approx(taban['htpb']['n'])
        assert m['a'] == pytest.approx(1.5 * taban['htpb']['a'])
        assert 'common exponent' in m['regression_rule']

    def test_yogunluk_HACIM_toplamiyla_kuruluyor(self, monkeypatch):
        """Kütle payından yoğunluk: 1/rho = sum(w_i/rho_i).

        Aritmetik ortalama (eski kural) yalnız HACİM payları için doğrudur.
        """
        mixer = cf.FuelMixtureSystem()
        taban = dict(mixer.base_fuels)
        taban['agir'] = {'density': 2000.0,
                         'a': taban['htpb']['a'],
                         'n': taban['htpb']['n']}
        monkeypatch.setattr(mixer, 'base_fuels', taban)
        m = mixer.create_mixture({'htpb': 0.5, 'agir': 0.5})
        beklenen = 1.0 / (0.5 / 920.0 + 0.5 / 2000.0)
        assert m['density'] == pytest.approx(beklenen)
        # Aritmetik ortalama 1460,0 olurdu — kural gerçekten değişmiş olmalı.
        assert m['density'] != pytest.approx(0.5 * 920.0 + 0.5 * 2000.0)
        assert 'volume-additive' in m['density_rule']

    def test_gecersiz_pay_reddedilir(self):
        mixer = cf.FuelMixtureSystem()
        with pytest.raises(ValueError):
            mixer.create_mixture({'htpb': True, 'paraffin': 0.0})


# ===========================================================================
# P10B1-16 — chug eşiğinin dördüncü (ve CANLI) kopyası
# ===========================================================================

class TestChugEsigiTekKaynak:

    def test_esik_TEK_KAYNAK_NESNESI(self):
        """Kopya değil, ithal edilmiş NESNE (sayıdan türetilmeyen iddia)."""
        assert cf.CHUG_DP_RATIO_MINIMUM is \
            acoustic_modes.CHUG_DP_RATIO_MINIMUM

    def test_common_fixes_kendi_sayisini_YAZMIYOR(self):
        """AST: ΔP bağlamında 0,15/0,20 sabiti yeniden doğarsa KIRMIZI."""
        agac = ast.parse(KOD_CF)
        ebeveyn = {}
        for ust in ast.walk(agac):
            for alt in ast.iter_child_nodes(ust):
                ebeveyn[alt] = ust
        satirlar = KOD_CF.splitlines()
        ihlal = []
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Constant):
                continue
            if not isinstance(dugum.value, float):
                continue
            if round(dugum.value, 10) not in (0.15, 0.20):
                continue
            satir = satirlar[dugum.lineno - 1]
            if re.search(r'(?i)dp|delta_p|pressure_drop|p_c|chamber_pressure',
                         satir):
                ihlal.append((dugum.lineno, satir.strip()))
        assert not ihlal, (
            'ΔP/Pc eşiği common_fixes içinde SAYI olarak yeniden doğmuş: '
            + '; '.join(f'{n}: {s}' for n, s in ihlal))

    # --- DAVRANIŞ: sayılar ölçülmüş vakalardır, üründen ithal EDİLMEZ ------
    @pytest.mark.parametrize('tank,pc,gecmeli', [
        (110.0, 100.0, False),   # ölçüldü: ΔP/Pc = 0,10 -> RET
        (120.0, 100.0, True),    # ölçüldü: ΔP/Pc = 0,20 -> GEÇ
        (48.0, 40.0, True),      # ölçüldü: ikinci ölçek, ΔP/Pc = 0,20 -> GEÇ
        (100.0, 100.0, False),   # tank = Pc -> birinci dal
    ])
    def test_kapi_davranisi_BIT_AYNI(self, tank, pc, gecmeli):
        gecti, mesaj = cf.CommonValidation.validate_pressure_consistency(
            tank, pc)
        assert gecti is gecmeli, (
            f'tank={tank}, Pc={pc}: kapı hükmü ölçülen vakadan saptı '
            f'({mesaj!r}).')

    def test_ret_metni_BIT_AYNI_kaldi(self):
        """Tek kaynağa bağlanma kullanıcıya giden cümleyi DEĞİŞTİRMEMELİ."""
        _, mesaj = cf.CommonValidation.validate_pressure_consistency(
            110.0, 100.0)
        assert mesaj == ('Insufficient pressure drop. Need at least 15.0 bar '
                         'drop for proper injection')


# ===========================================================================
# P10B1-17 — bool deliği
# ===========================================================================

class TestToplamImpulsKapisi:

    def test_bool_thrust_REDDEDILIR(self):
        """ÖLÇÜLEN KUSUR: thrust=True -> total_impulse 10,0 N*s."""
        with pytest.raises(InputError) as e:
            cf.CommonCalculations.calculate_total_impulse_auto(True, 10.0,
                                                               None)
        assert "'thrust'" in str(e.value)
        assert 'bool' in str(e.value)

    def test_bool_burn_time_de_REDDEDILIR(self):
        with pytest.raises(InputError) as e:
            cf.CommonCalculations.calculate_total_impulse_auto(1000.0, True,
                                                               None)
        assert "'burn_time'" in str(e.value)

    @pytest.mark.parametrize('deger', [float('nan'), float('inf'),
                                       float('-inf')])
    def test_sonlu_olmayan_REDDEDILIR(self, deger):
        """ÖLÇÜLEN KUSUR: thrust=NaN -> total_impulse NaN (sessiz)."""
        with pytest.raises(InputError):
            cf.CommonCalculations.calculate_total_impulse_auto(deger, 10.0,
                                                               None)

    @pytest.mark.parametrize('t,b', [(1000.0, 0.0), (0.0, 10.0),
                                     (-1000.0, 10.0), (1000.0, -10.0)])
    def test_pozitif_olmayan_REDDEDILIR(self, t, b):
        """ÖLÇÜLEN KUSUR: burn_time=0 -> 0,0 N*s; thrust=-1000 -> -10000."""
        with pytest.raises(InputError) as e:
            cf.CommonCalculations.calculate_total_impulse_auto(t, b, None)
        assert 'greater than zero' in str(e.value)

    def test_hata_ALANI_ADLANDIRIYOR(self):
        with pytest.raises(InputError) as e:
            cf.CommonCalculations.calculate_total_impulse_auto(1000.0, 0.0,
                                                               None)
        assert "'burn_time'" in str(e.value)

    def test_gecerli_girdi_HALA_calisiyor(self):
        """Kapı fail-closed ama kapalı-takılı değil."""
        d = cf.CommonCalculations.calculate_total_impulse_auto(1000.0, 10.0,
                                                              None)
        assert d['total_impulse'] == pytest.approx(10000.0)
        d = cf.CommonCalculations.calculate_total_impulse_auto(None, 10.0,
                                                              10000.0)
        assert d['thrust'] == pytest.approx(1000.0)
        d = cf.CommonCalculations.calculate_total_impulse_auto(1000.0, None,
                                                              10000.0)
        assert d['burn_time'] == pytest.approx(10.0)

    def test_deponun_kendi_kapisini_cagiriyor(self):
        """input_guard yeniden yazılmamış, İTHAL edilmiş olmalı."""
        assert 'input_guard' in KOD_CF
        assert '_ig.num(' in KOD_CF


# ===========================================================================
# P10B1-18 — boş girdiden uydurma ihraç dosyası
# ===========================================================================

#: Ölçülen uydurma .eng künye satırı (28 Ağu 2026).
UYDURMA_ENG_SATIRI = '100.0 300.0 0 5.000 10.000 HRMA'


class TestIhracFailClosed:

    def test_bos_girdide_eng_URETILMEZ(self):
        with pytest.raises(ValueError) as e:
            cf.ExportFixes.generate_motor_file({})
        metin = str(e.value)
        for alan in ('motor_name', 'diameter', 'length', 'propellant_mass',
                     'total_mass', 'thrust_curve'):
            assert alan in metin, (
                f'Ret gerekçesi eksik alanı adlandırmıyor: {alan}')

    def test_uydurma_satir_artik_uretilemiyor(self):
        """Ölçülen çıktının kendisi bir daha doğmamalı."""
        try:
            uretilen = cf.ExportFixes.generate_motor_file({})
        except ValueError:
            uretilen = ''
        assert UYDURMA_ENG_SATIRI not in uretilen

    def test_eksik_TEK_alan_da_yeter(self):
        tam = {'motor_name': 'X', 'diameter': 100.0, 'length': 300.0,
               'propellant_mass': 5.0, 'total_mass': 10.0,
               'thrust_curve': [(0.0, 0.0), (1.0, 100.0)]}
        for alan in tam:
            eksik = {k: v for k, v in tam.items() if k != alan}
            with pytest.raises(ValueError) as e:
                cf.ExportFixes.generate_motor_file(eksik)
            assert alan in str(e.value)

    def test_tam_girdide_dosya_URETILIYOR(self):
        tam = {'motor_name': 'HRMA_TEST', 'diameter': 98.0, 'length': 500.0,
               'propellant_mass': 2.5, 'total_mass': 4.0,
               'thrust_curve': [(0.0, 0.0), (0.1, 900.0), (3.0, 900.0),
                                (3.1, 0.0)]}
        eng = cf.ExportFixes.generate_motor_file(tam)
        assert '98.0 500.0 0 2.500 4.000 HRMA' in eng
        assert 'HRMA_TEST' in eng
        assert eng.rstrip().endswith(';')

    def test_kutle_celiskisi_reddedilir(self):
        tam = {'motor_name': 'X', 'diameter': 98.0, 'length': 500.0,
               'propellant_mass': 9.0, 'total_mass': 4.0,
               'thrust_curve': [(0.0, 0.0), (1.0, 100.0)]}
        with pytest.raises(ValueError) as e:
            cf.ExportFixes.generate_motor_file(tam)
        assert 'total_mass' in str(e.value)

    def test_bos_girdide_stl_URETILMEZ(self):
        with pytest.raises(ValueError) as e:
            cf.ExportFixes.generate_basic_stl({})
        assert 'chamber_length' in str(e.value)
        assert 'chamber_diameter' in str(e.value)

    def test_tam_girdide_stl_URETILIYOR(self):
        stl = cf.ExportFixes.generate_basic_stl(
            {'chamber_length': 500.0, 'chamber_diameter': 98.0})
        assert stl.startswith('solid motor_assembly')
        assert '98.0' in stl

    def test_kanonik_yaziciya_YONLENDIRIYOR(self):
        """Bu eski yardımcı canlandırılmadı; kanonik yazıcı adıyla anılmalı."""
        assert 'openrocket_integration' in KAYNAK_CF, (
            'Kanonik .eng yazıcısı bu modülde artık anılmıyor.')


# ===========================================================================
# ÖLÜ KOL BEYANI — sessiz bırakmak çözüm değil
# ===========================================================================

class TestOluKolBeyani:

    def test_modul_kendi_urun_yerini_BEYAN_EDIYOR(self):
        """``fuel_mixer``/``export_fixes``/``calculations`` ürün akışında ölü.

        Bu ölçüm modülün başlığında YAZILI olmalı; ileride biri bu kolları
        bağlarsa beyanın da güncellenmesi gerekir.
        """
        baslik = ast.get_docstring(ast.parse(KAYNAK_CF)) or ''
        assert 'validate_pressure_consistency' in baslik
        for ad in ('fuel_mixer', 'export_fixes', 'calculations'):
            assert ad in baslik, (
                f'{ad} kolunun ürün akışındaki yeri beyan edilmemiş.')
