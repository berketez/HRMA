"""ÖH Dalga-20 / altyapi aşama 1 — bekçiler.

Kapsanan kalemler
-----------------
P10B4-15  Kaynak seviyesi sabit envanteri çıkaran araç YOKTU; ``9.81`` ⟷
          ``9.80665`` çelişkisi ürünün ön yüzünde canlıydı ve hiçbir bekçi
          onu görmüyordu. Araç kuruldu (``tools/sabit_envanteri.py``),
          envanter kilitlendi, iki BİT-AYNI ikiz merkeze bağlandı.
P10B4-02  ``iddia_lint``in kaçırdığı "NASA **CEA** Validated" iddiası artık
          görülüyor (D17 onarımı); bu bekçi onarımın YERİNDE DURDUĞUNU ve
          iddia envanterinin BÜYÜMEDİĞİNİ kilitler.
P10B4-16  Araç bekçi envanteri: partinin 12 aracının 2'si hiçbir otomasyonda
          koşmuyordu. İkisi de sözleşme bekçisine bağlandı.
P15B2-05  ``hrma/constants.py``nin 27 adının yalnız 3'ü bekçiliydi.

Ölçüm betiği: ``docs/scofield/raw/OH/D20/altyapi/a1/olcum.py``
(önce.json / sonra.json).
"""

from __future__ import annotations

import ast
import gzip
import json
import pathlib
import struct
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / 'tools'))

import sabit_envanteri  # noqa: E402


# ---------------------------------------------------------------------------
# P10B4-15 — kaynak seviyesi sabit envanteri
# ---------------------------------------------------------------------------

#: ÖLÇÜLMÜŞ envanter (docs/scofield/raw/OH/D20/altyapi/a1/sonra.json).
#: Anahtar: (dosya, sabit, değer, tür). Satır numarası KULLANILMAZ — kayar.
#: Bu liste bir MANDAL'dır: küçülebilir (kalem onarıldıkça), BÜYÜYEMEZ.
#: Her satırın sonundaki kulvar, kalemi onarabilecek sahibi gösterir.
KILITLI_ENVANTER = [
    ('hrma/app.py', 'G_0', 9.80665, 'ikiz'),                      # app-api
    ('hrma/data/chemical_database.py', 'R_STAR_ICAO', 8.314, 'yakin_iska'),
    ('hrma/data/chemical_database.py', 'R_STAR_ICAO', 8.314, 'yakin_iska'),
    ('hrma/data/chemical_database.py', 'R_STAR_ICAO', 8.314, 'yakin_iska'),
    ('hrma/data/external_data_fetcher.py', 'R_UNIVERSAL', 8314.5, 'yakin_iska'),
    ('hrma/data/external_data_fetcher.py', 'R_UNIVERSAL', 8314.5, 'yakin_iska'),
    ('hrma/data/external_data_fetcher.py', 'R_UNIVERSAL', 8314.5, 'yakin_iska'),
    ('hrma/data/external_data_fetcher.py', 'R_UNIVERSAL', 8314.5, 'yakin_iska'),
    ('hrma/data/materials_db.py', 'G_0', 9.8, 'yakin_iska'),
    ('hrma/data/materials_db.py', 'G_0', 9.8, 'yakin_iska'),
    ('hrma/engines/hybrid_rocket_engine.py', 'R_UNIVERSAL', 8314.462618, 'ikiz'),
    ('hrma/engines/hybrid_rocket_engine.py', 'R_UNIVERSAL', 8314.462618, 'ikiz'),
    ('hrma/engines/hybrid_rocket_engine.py', 'R_UNIVERSAL', 8314.462618, 'ikiz'),
    ('hrma/static/js/app.js', 'G_0', 9.81, 'yakin_iska'),
    ('hrma/static/js/app.js', 'G_0', 9.81, 'yakin_iska'),
    ('hrma/static/js/panels/cfd_panel.js', 'R_UNIVERSAL', 8314.462618, 'ikiz'),
    ('hrma/static/js/panels/feed_panel.js', 'G_0', 9.81, 'yakin_iska'),
    ('hrma/static/js/panels/performance_panel.js', 'G_0', 9.80665, 'ikiz'),
    ('hrma/static/js/panels/performance_panel.js', 'G_0', 9.80665, 'ikiz'),

    # ---- ÖH D26 / ihracat a1 (defter P15B2-06 kalanı) ----
    # BU ONBİR SATIR YENİ BİR KUSUR DEĞİL, YENİ GÖRÜLEN BİR KUSURDUR.
    # Deniz seviyesi basıncının merkezde adı yoktu; ``hrma/data`` altındaki
    # beş ``101325`` literali merkeze bağlanırken sabit
    # ``constants.P_SEA_LEVEL_PA = ISA_LAYERS[0][3]`` olarak tanımlandı
    # (tabloya ikinci bir literal yazılmadı). ``tools/sabit_envanteri.py``
    # o güne kadar TABLODAN OKUMA (``Subscript``) ile tanımlı sabitleri
    # göremiyordu — P10B3-10'da ``BinOp`` için kapatılan kör bandın ikinci
    # ayağı; araç genişletildi (``_yapi_ogesi``).
    #
    # ÖLÇÜLDÜ (taban 7751531, ihracat a1 kanıt dizini): aşağıdaki sekiz
    # dosyadaki ``101325`` literalleri TABANDA DA VARDI (``grep -c``: 2, 1,
    # 1, 1, 4, 2, 1, 1). Yani envanter büyümedi; aracın körlüğü kalktı ve
    # var olan borç adıyla kilitlendi. Onarım bu kulvarın sahasında değil;
    # her satırın sahibi yanında yazılıdır.
    #
    # ÖH D27 / termo-ucus a1 (OH-D26-01, P15B2-06 ÜÇÜNCÜ AYAK) — SEKİZ
    # SATIR DÜŞTÜ, mandal 11 -> 3. Bu bir GEVŞETME değil DARALTMADIR
    # (ÖK-22 uyumlu; küme tek yönlüdür, küçülebilir). Ödenen borç listede
    # TUTULMAZ: bayat bir satır, ileride aynı adla dönen körlüğü sessizce
    # affeder. Kalkan satırlar ve yerine geçen tek kaynak:
    #   nozzle_flow_1d.py       ×2  -> ``ambient_pressure`` varsayılanları
    #   six_dof_trajectory.py   ×1  -> ISA döngü tohumu (tablo taban satırı)
    #   pressurant_sizing.py    ×1  -> NBP doygunluğu (TANIM gereği 1 atm)
    #   water_hammer.py         ×1  -> LOX ``vapor_pressure_Pa`` (NBP)
    #   record_adapters.py      ×1  -> ``UNIT_TO_SI['atm']`` (atm TANIMI)
    #   advanced_results.py     ×1  -> ``SEA_LEVEL_AMBIENT_PA``
    #   visualization.py        ×1  -> ``NOZZLE_FIG_AMBIENT_PA``
    # ÖLÇÜLDÜ (docs/scofield/raw/OH/D27/termo-ucus/a1/{once,sonra}.json):
    # sahada çıplak ``101325`` literali 8 -> 0, merkezden ithal eden dosya
    # 0 -> 7, sekiz kullanımın DEĞERİ bit-aynı (101325,0). ``hrma/app.py``
    # üç satırı app-api sahasıdır ve DOKUNULMADI — kilitte kalır.
    ('hrma/app.py', 'P_SEA_LEVEL_PA', 101325.0, 'ikiz'),          # app-api
    ('hrma/app.py', 'P_SEA_LEVEL_PA', 101325.0, 'ikiz'),          # app-api
    ('hrma/app.py', 'P_SEA_LEVEL_PA', 101325.0, 'ikiz'),          # app-api
]


@pytest.fixture(scope='module')
def envanter():
    return sabit_envanteri.envanter(KOK)


def _anahtarlar(ihlaller):
    return sorted((i['dosya'], i['sabit'], i['deger'], i['tur'])
                  for i in ihlaller)


class TestP10B415KaynakSabitEnvanteri:
    """Araç var, kör bandı yok, envanteri kilitli."""

    def test_arac_merkezi_KOPYALAMIYOR(self):
        """Değerler ``hrma/constants.py``den okunur, araca yazılmaz.

        Aracın kendisi ikinci tanım noktası olsaydı, merkez değiştiğinde
        bekçi eski değere göre hüküm verirdi — kusuru ölçmesi gereken araç
        kusurun taşıyıcısı olurdu.
        """
        kaynak = (KOK / 'tools' / 'sabit_envanteri.py').read_text(encoding='utf-8')
        agac = ast.parse(kaynak)
        yazili = set()
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Constant) and isinstance(dugum.value, float):
                yazili.add(dugum.value)
        from hrma.constants import G_0, R_UNIVERSAL, STEFAN_BOLTZMANN
        # Meşru muafiyet tablosu (WGS-84 vb.) dışında merkezî DEĞER yazılamaz.
        for deger, ad in ((G_0, 'G_0'), (R_UNIVERSAL, 'R_UNIVERSAL'),
                          (STEFAN_BOLTZMANN, 'STEFAN_BOLTZMANN')):
            assert deger not in yazili, (
                'sabit_envanteri.py %s değerini (%r) KOPYALAMIŞ; merkezden '
                'okunmalı.' % (ad, deger))

    def test_kor_band_KAPALI_Assign_disi_bicimleri_goruyor(self, tmp_path):
        """``ast.Assign`` yetmez — asıl kusur hesabın ORTASINDA durur.

        Yalnız atamaya bakan bir tarayıcı bu depoda 19 isabetin 3'ünü görür.
        Bu iddia sentetik dosyayla ölçer: aynı değer beş ayrı sözdizimsel
        bağlamda geçer, tarayıcı beşini de görmelidir.
        """
        sahte = tmp_path / 'hrma'
        (sahte / 'engines').mkdir(parents=True)
        (tmp_path / 'hrma' / 'constants.py').write_text(
            'G_0 = 9.80665\nR_UNIVERSAL = 8314.462618\n', encoding='utf-8')
        (sahte / 'engines' / 'ornek.py').write_text(
            'ATAMA = 9.80665\n'
            'def f(g=9.80665):\n'
            '    return 8314.462618 / g\n'
            'D = {"g": 9.80665}\n'
            'X = 9.80665 if True else 0.0\n'
            'y = f(g=8314.462618)\n', encoding='utf-8')
        r = sabit_envanteri.envanter(tmp_path)
        bicimler = {i['bicim'] for i in r['ihlaller']}
        assert 'Assign' in bicimler
        assert bicimler - {'Assign'}, (
            'Tarayıcı yalnız Assign görüyor — kör band AÇIK. Görülen: %s'
            % sorted(bicimler))
        assert len(bicimler) >= 4, (
            'Beş bağlamın en az dördü ayrı biçim olarak künyelenmeli; '
            'görülen: %s' % sorted(bicimler))

    def test_yakin_iska_ikizden_AYRI_siniflaniyor(self, tmp_path):
        """``9.81`` ile ``9.80665`` aynı kusur değildir.

        İkiz sessizdir (sayı doğru, kaynak ikiye bölünmüş); yakın-ıska
        gürültülüdür (ürün aynı fiziksel sabit için İKİ FARKLI sayı
        kullanıyor). Tarayıcı ikisini karıştırırsa onarım sırası kaybolur.
        """
        (tmp_path / 'hrma').mkdir()
        (tmp_path / 'hrma' / 'constants.py').write_text(
            'G_0 = 9.80665\n', encoding='utf-8')
        (tmp_path / 'hrma' / 'a.py').write_text(
            'AYNI = 9.80665\nYAKIN = 9.81\nUZAK = 3.0\n', encoding='utf-8')
        r = sabit_envanteri.envanter(tmp_path)
        turler = {i['deger']: i['tur'] for i in r['ihlaller']}
        assert turler.get(9.80665) == 'ikiz'
        assert turler.get(9.81) == 'yakin_iska'
        assert 3.0 not in turler, 'ilgisiz sayı kusur sayılmış'

    def test_envanter_BUYUMEZ(self, envanter):
        """Mandal: yeni çıplak sabit girerse KIRMIZI.

        Liste küçülebilir (kalem onarıldıkça); büyüyemez.
        """
        simdi = _anahtarlar(envanter['ihlaller'])
        kilit = sorted(KILITLI_ENVANTER)
        yeni = [k for k in simdi if simdi.count(k) > kilit.count(k)]
        assert not yeni, (
            'YENİ çıplak sabit kullanımı girdi (kilitte olmayan): %s\n'
            'Merkezden import et (hrma.constants) ya da meşruysa '
            'tools/sabit_envanteri.py::MESRU listesine GEREKÇESİYLE ekle.'
            % sorted(set(yeni)))
        assert len(simdi) <= len(kilit), (
            'envanter %d -> %d büyüdü' % (len(kilit), len(simdi)))

    def test_mesru_muafiyetlerin_GEREKCESI_var(self):
        """Gerekçesiz muafiyet kör banddır — her satır ölçülmüş olmalı."""
        assert sabit_envanteri.MESRU, 'muafiyet tablosu boş olamaz'
        for m in sabit_envanteri.MESRU:
            assert set(m) == {'dosya', 'sabit', 'deger', 'gerekce'}
            assert len(m['gerekce']) >= 40, (
                '%s muafiyetinin gerekçesi bir cümle bile değil' % m['dosya'])

    def test_ISA_TABLE_TOP_M_ikizleri_MERKEZDEN_geliyor(self):
        """D20 onarımı: iki dosyadaki BİT-AYNI 84852.0 ikizi kalktı."""
        from hrma.constants import ISA_TABLE_TOP_M
        for yol in ('hrma/analysis/six_dof_trajectory.py',
                    'hrma/analysis/trajectory_analysis.py'):
            metin = (KOK / yol).read_text(encoding='utf-8')
            assert 'ISA_TABLE_TOP_M' in metin, '%s merkezi ithal etmiyor' % yol
            assert 'H_TABLE_TOP = 84852.0' not in metin, (
                '%s içinde çıplak 84852.0 ikizi geri gelmiş' % yol)
        import hrma.analysis.six_dof_trajectory as sdt
        import hrma.analysis.trajectory_analysis as ta
        assert sdt.ISA_TABLE_TOP_M is ISA_TABLE_TOP_M
        assert ta.ISA_TABLE_TOP_M is ISA_TABLE_TOP_M


# ---------------------------------------------------------------------------
# P15B2-05 — hrma/constants.py bekçi kapsamı
# ---------------------------------------------------------------------------

#: Merkezde tanımlı ama ürün kodunda HİÇ ithal edilmeyen adlar (ölçüldü).
#: Ölü merkezî sabit zararsız değildir: okuyan "burası tek kaynak" sanır,
#: oysa ürün başka bir sayı kullanıyor olabilir. Liste büyüyemez.
KILITLI_OLU_SABITLER = {
    'C_STAR_BAND_DEFAULT_MPS', 'C_STAR_PLAUSIBLE_BAND_MPS', 'H_TROPOPAUSE',
    'LAMBDA_CONICAL_15DEG', 'LAMBDA_CONICAL_20DEG', 'L_STAR_GENERIC_BAND_M',
    'L_STAR_GENERIC_BAND_SOURCE', 'P_TROPOPAUSE', 'R_universal',
    'T_TROPOPAUSE', 'g0', 'g_0',
}


def _constants_adlari():
    agac = ast.parse((KOK / 'hrma' / 'constants.py').read_text(encoding='utf-8'))
    adlar = []
    for dugum in agac.body:
        if isinstance(dugum, ast.Assign):
            adlar += [t.id for t in dugum.targets if isinstance(t, ast.Name)]
        elif isinstance(dugum, ast.AnnAssign) and isinstance(dugum.target, ast.Name):
            adlar.append(dugum.target.id)
    return adlar


class TestP15B205SabitBekcisi:
    """27 adın tamamı bekçi altında (ölçümde 3/27 idi)."""

    def test_her_ad_TEK_kez_atanmis(self):
        adlar = _constants_adlari()
        yinelenen = sorted({a for a in adlar if adlar.count(a) > 1})
        assert not yinelenen, (
            'hrma/constants.py içinde İKİ KEZ atanan ad: %s — merkezin '
            'kendisi ikinci tanım noktası olamaz.' % yinelenen)

    def test_takma_adlar_merkezle_AYNI_nesne(self):
        """Geriye uyum takma adları sapmamalı."""
        from hrma import constants as c
        assert c.g_0 is c.G_0 and c.g0 is c.G_0
        assert c.R_universal is c.R_UNIVERSAL
        assert c.MOTOR_TYPE_SET == set(c.MOTOR_TYPES)
        assert c.BAR_PER_PA == pytest.approx(1.0 / c.PA_PER_BAR, rel=1e-15)

    def test_TUM_sabitler_bekci_kapsaminda(self, envanter):
        """Kapsam mandalı: her ad ya taranıyor ya BEYAN EDİLMİŞ kapsam dışı.

        Ölçümde 27 adın 24'ü hiçbir bekçide geçmiyordu. Artık her ad ya
        ``sabit_envanteri`` taramasında (ayırt edici), ya belirsiz-değer
        beyanında, ya da sayısal olmadığı için tür kapısında.
        """
        adlar = set(_constants_adlari())
        from hrma import constants as c
        sayisal = {a for a in adlar
                   if isinstance(getattr(c, a), (int, float))
                   and not isinstance(getattr(c, a), bool)}
        kapsanan = set(envanter['sabitler']) | set(envanter['belirsiz_deger'])
        eksik = sayisal - kapsanan
        assert not eksik, (
            'Sayısal sabit bekçi kapsamı DIŞINDA: %s' % sorted(eksik))
        # Sayısal olmayanlar (tablo/demet/künye) ayrıca adıyla anılmalı.
        #
        # ÖH D30 / fix-29a — BURASI ELLE YAZILI BİR KİLİT LİSTESİYDİ ve
        # merkeze meşru bir tablo/künye eklendiğinde (D29: ortam sıcaklığı
        # bandı) listeyi güncellemeyi unutmak KIRMIZI üretiyordu; daha
        # kötüsü, listeye ad eklemek "sınandı" anlamına geliyordu — tam da
        # OH-D25-01(c)'nin kapattığı "ad geçişi = kapsam" yanılsaması.
        # Ölçüt artık aracın KENDİ kapsam tanımıdır (``bekci_kapsami``in
        # ``govde`` kümesi: adı bir test GÖVDESİNDE geçenler); ikinci bir
        # elle liste tutulmaz (Doktrin 4).
        kapsam = sabit_envanteri.bekci_kapsami(KOK)
        sayisal_olmayan = adlar - sayisal
        disarida = sorted(sayisal_olmayan - set(kapsam['govde']))
        assert not disarida, (
            'Bekçiye tanıtılmamış sayısal-olmayan sabit: %s — bir bekçi '
            'GÖVDESİNDE adıyla sınanmalı (muafiyet literaline yazmak '
            'sınamak değildir).' % disarida)

    def test_olu_merkezi_sabit_listesi_BUYUMEZ(self):
        """Kimsenin ithal etmediği merkezî sabitler — mandal.

        ÖH D30 / fix-29a — ÖLÇÜT GENİŞLEDİ (gerekçeli, fail-closed).
        ``X_SOURCE`` biçimindeki KÜNYE sabitleri hiçbir zaman ithal
        edilmez: onlar bir DEĞERİ değil o değerin kaynağını taşır ve
        ürünün ilgili tablosu onlara ADIYLA atıf yapar. Ölçüldü (taban
        ab7cf68b): ``AMBIENT_TEMPERATURE_BAND_SOURCE`` bu yüzden "ölü"
        görünüyordu, oysa belgelediği bant
        (``AMBIENT_TEMPERATURE_BAND_K``) ürün tarafından İTHAL EDİLİYOR
        (``hrma/validation/motor_validation.py``) ve künyenin ADI aynı
        tablonun gerekçesinde geçiyor. Muafiyet ANONİM DEĞİL: iki bağın
        İKİSİ de ölçülür, biri koparsa kırmızı yanar. Eşlikçisi
        tüketilmeyen künye (``L_STAR_GENERIC_BAND_SOURCE``) bu kapıdan
        geçmez — kilit listesindeki yerini korur.
        """
        import subprocess

        def _urunde_geciyor(desen, merkez_haric=False):
            # ``merkez_haric``: künye atıfları için ZORUNLU — bir adın
            # KENDİ tanım satırı (hrma/constants.py) atıf sayılamaz,
            # yoksa her künye kendi kendini canlı ilan ederdi.
            yol = ['hrma/'] + ([':!hrma/constants.py'] if merkez_haric else [])
            r = subprocess.run(['git', 'grep', '-l', '-P', desen, '--']
                               + yol, cwd=KOK, capture_output=True, text=True)
            return bool(r.stdout.strip())

        adlar = _constants_adlari()
        olu = set()
        for ad in adlar:
            if _urunde_geciyor(
                    r'from hrma\.constants import [^\n]*\b%s\b'
                    r'|constants\.%s\b' % (ad, ad)):
                continue
            # KÜNYE EŞLİKÇİSİ: belgelediği sabit üründe tüketiliyor mu ve
            # künyenin kendi adına üründe atıf var mı?
            if ad.endswith('_SOURCE'):
                govde = ad[:-len('_SOURCE')]
                eslikciler = [a for a in adlar
                              if a != ad and a.startswith(govde)]
                if eslikciler and all(
                        _urunde_geciyor(
                            r'from hrma\.constants import [^\n]*\b%s\b'
                            r'|constants\.%s\b' % (e, e))
                        for e in eslikciler) and _urunde_geciyor(
                            r'\b%s\b' % ad, merkez_haric=True):
                    continue
            olu.add(ad)
        yeni = olu - KILITLI_OLU_SABITLER
        assert not yeni, (
            'Merkeze eklenip HİÇ kullanılmayan yeni sabit: %s — ya tüket ya '
            'ekleme (ölü merkezî sabit "tek kaynak" yanılsaması üretir).'
            % sorted(yeni))


# ---------------------------------------------------------------------------
# P10B4-16 — araç bekçi envanteri (12 aracın 2'si otomasyonsuzdu)
# ---------------------------------------------------------------------------

class TestP10B416AracOtomasyonu:
    """Kaynak varlık araçları ile SEVK EDİLEN veri aynı sözleşmede mi?

    Bu iki araç ağ indirmesi yapar, testte koşturulamaz. Koşturulamayan bir
    aracı "bekçili" saymanın tek dürüst yolu, aracın BEYAN ETTİĞİ sözleşme
    ile depoda SEVK EDİLEN ürünün aynı olduğunu ölçmektir: araç değişip veri
    değişmezse (ya da tersi) bu bekçi kırmızı verir.
    """

    def test_dem_araci_ile_sevk_edilen_veri_AYNI_geometride(self):
        import build_launch_site_dem as dem
        meta_yolu = KOK / 'hrma' / 'data' / 'dem' / dem.META_NAME
        assert meta_yolu.exists(), 'sevk edilen DEM künyesi yok: %s' % meta_yolu
        meta = json.loads(meta_yolu.read_text(encoding='utf-8'))
        assert meta['nlat'] == dem.OUT_NLAT
        assert meta['nlon'] == dem.OUT_NLON
        assert meta['raw_bytes'] == dem.OUT_NLAT * dem.OUT_NLON * 2
        assert meta['binary_file'] == dem.BIN_NAME
        assert str(dem.DEEP_QUANT_THRESHOLD_M) in meta['deep_ocean_quantization']
        assert str(dem.DEEP_QUANT_STEP_M) in meta['deep_ocean_quantization']
        assert str(dem.STRIDE) in meta['resample_method']
        assert str(dem.OFFSET) in meta['resample_method']

    def test_dem_ikili_dosyasi_BEYAN_EDILEN_boyutta(self):
        """Künye 2160x4320 int16 diyorsa dosya tam o kadar bayt olmalı."""
        import build_launch_site_dem as dem
        ikili = KOK / 'hrma' / 'data' / 'dem' / dem.BIN_NAME
        with gzip.open(ikili, 'rb') as fh:
            bayt = 0
            while True:
                parca = fh.read(1 << 20)
                if not parca:
                    break
                bayt += len(parca)
        assert bayt == dem.OUT_NLAT * dem.OUT_NLON * 2, (
            'DEM yükü %d bayt; beyan %d x %d x 2 = %d'
            % (bayt, dem.OUT_NLAT, dem.OUT_NLON,
               dem.OUT_NLAT * dem.OUT_NLON * 2))

    def test_dem_derin_okyanus_nicemlemesi_beyani_uyguluyor(self):
        """Saf işlev: eşiğin altı adıma yuvarlanır, üstü DOKUNULMAZ."""
        np = pytest.importorskip('numpy')
        import build_launch_site_dem as dem
        grid = np.array([[-4321, -501, -499, 0, 137]], dtype=np.int16)
        sonuc = dem._quantize_deep_ocean(grid.copy())
        assert sonuc[0, 0] == -4300     # -500'den derin -> 100 m adım
        assert sonuc[0, 1] == -500
        assert list(sonuc[0, 2:]) == [-499, 0, 137], 'sığ/kara değeri bozuldu'

    def test_varlik_araci_sinir_ondaligi_SEVK_EDILEN_json_ile_ayni(self):
        import build_launch_site_assets as va
        sinir = KOK / 'hrma' / 'static' / 'img' / 'earth_borders.json'
        assert sinir.exists()
        veri = json.loads(sinir.read_text(encoding='utf-8'))
        assert veri['layers'], 'sınır dosyasında katman yok'

        def _sayilar(dugum):
            if isinstance(dugum, (int, float)):
                yield float(dugum)
            elif isinstance(dugum, list):
                for c in dugum:
                    yield from _sayilar(c)
            elif isinstance(dugum, dict):
                for c in dugum.values():
                    yield from _sayilar(c)

        ondalik = 0
        ornek = 0
        for deger in _sayilar(veri['layers']):
            s = repr(deger)
            if '.' in s and 'e' not in s:
                ondalik = max(ondalik, len(s.split('.')[1].rstrip('0')))
            ornek += 1
        assert ornek > 0, 'sınır dosyasından koordinat okunamadı'
        assert ornek == veri['point_count'] * 2, (
            'künye %d nokta diyor, dosyada %d koordinat var'
            % (veri['point_count'], ornek))
        assert ondalik <= va.COORD_DECIMALS, (
            'sevk edilen sınır dosyası %d ondalık taşıyor; araç %d beyan '
            'ediyor — araç ile veri ayrışmış' % (ondalik, va.COORD_DECIMALS))

    def test_blue_marble_dokusu_IKININ_KUVVETI(self):
        """WebGL1 mipmap şartı: POT olmayan doku çalışma anında ölçeklenir."""
        jpg = KOK / 'hrma' / 'static' / 'img' / 'blue_marble_4096.jpg'
        assert jpg.exists()
        ham = jpg.read_bytes()
        genislik = yukseklik = None
        i = 2
        while i < len(ham) - 9:
            if ham[i] != 0xFF:
                i += 1
                continue
            isaret = ham[i + 1]
            if isaret in (0xC0, 0xC1, 0xC2, 0xC3):
                yukseklik, genislik = struct.unpack('>HH', ham[i + 5:i + 9])
                break
            if isaret in (0xD8, 0xD9) or 0xD0 <= isaret <= 0xD7:
                i += 2
                continue
            i += 2 + struct.unpack('>H', ham[i + 2:i + 4])[0]
        assert genislik and yukseklik, 'JPEG boyutu okunamadı'
        assert genislik & (genislik - 1) == 0, 'genişlik POT değil: %d' % genislik
        assert yukseklik & (yukseklik - 1) == 0, 'yükseklik POT değil: %d' % yukseklik
        assert genislik == 2 * yukseklik, (
            'eşdikdörtgen doku 2:1 olmalı: %dx%d' % (genislik, yukseklik))


# ---------------------------------------------------------------------------
# P10B4-02 — kazanılmamış "NASA CEA Validated" iddiası
# ---------------------------------------------------------------------------

#: D17'de onarılan kuralın BUGÜN gördüğü iddialar (satır karması ile
#: kilitli: metin sessizce değişirse karma tutmaz). Sahibi: arayüz kulvarı
#: (i18n anahtar dosyaları + şablon). Liste büyüyemez.
# ÖH D21 / arayuz a1 — BORÇ ÖDENDİ, MANDAL SIKILDI. D20'de burada yedi
# kayıt vardı ve altısı kazanılmamış "NASA CEA doğrulandı" hükmüydü; onların
# sahibi arayüz kulvarıydı ve o kulvar bu dalgada hepsini üründen söktü
# (ölçüm: docs/scofield/raw/OH/D21/arayuz/a1/{once,sonra}.json, M1 —
# cea_validated isabeti 7 -> 0, aracın kör bandındaki hükümler 8 -> 0).
# Geriye YALNIZ künye borcu kalır: `adv.tip.densityKgM` ipucu yoğunluğun
# "built-in propellant table"dan geldiğini söylüyor; bu iddia ölçülerek
# DOĞRU bulundu (hrma/app.py::oxidizer_reference_density `source` künyesi
# yayımlıyor), o yüzden metin korunur ve kayıt borç mandalı olarak durur.
KILITLI_IDDIALAR = {
    ('hrma/static/js/i18n_advanced.js', 'builtin_table_claim', 'f74526f0e7de'),
}

IDDIA_HEDEFLERI = ('hrma/templates/index.html', 'hrma/static/js/i18n.js',
                   'hrma/static/js/i18n_advanced.js')


def _iddia_bulgulari():
    from tools import iddia_lint
    bulgular = []
    for hedef in IDDIA_HEDEFLERI:
        bulgular.extend(iddia_lint.scan_file(str(KOK / hedef)))
    return bulgular


class TestP10B402KazanilmamisIddia:

    def test_kural_ARAYA_SOZCUK_GIRSE_de_goruyor(self, tmp_path):
        """D17 onarımı yerinde mi: "NASA **CEA** Validated" yakalanıyor mu?

        Kusur, desenin ``NASA[-\\s]validated`` olmasıydı; araya bir sözcük
        girince kopuyor ve ürünün açılış ekranındaki iddia 0 isabet
        veriyordu.

        ÖH D21 / arayuz a1 — ÇEVRİLDİ. Bu iddia ARACIN yeteneğini ÜRÜNÜN
        KUSURU üzerinden ölçüyordu: geçmek için açılış ekranında bir
        "NASA CEA Validated" isabeti BULUNMASI gerekiyordu. Yani kusuru
        koruyan bir bekçiydi; arayüz kulvarı iddiayı söker sökmez kırmızı
        verdi. Aracın yeteneği artık FİKSTÜR üzerinde ölçülür (ürünün
        temiz olması bu ölçümü bozmaz) ve ayrıca ürünün gerçekten
        temizlendiği kilitlenir.
        """
        fikstur = tmp_path / 'iddia_fikstur.js'
        fikstur.write_text(
            "// tarihsel biçimler — hepsi kazanılmamış CEA uyum hükmüdür\n"
            "var a = 'Parametric Solvers · NASA CEA Validated · 3D';\n"
            "var b = 'Data will be validated against NASA CEA database.';\n"
            "var c = 'Yakıt bileşimi NASA CEA ile doğrulandı';\n",
            encoding='utf-8')
        from tools import iddia_lint
        metinler = {f.matched for f in iddia_lint.scan_file(str(fikstur))}
        assert any('CEA' in m and 'alidated' in m for m in metinler), (
            'Araya sözcük giren "NASA CEA Validated" biçimi yine kaçıyor; '
            'görülen eşleşmeler: %s' % sorted(metinler))
        assert len(metinler) >= 3, sorted(metinler)
        # ÜRÜN tarafı: aynı hükmün üç hedef dosyada SIFIR isabeti kalmalı.
        urun = [b for b in _iddia_bulgulari() if b.rule_id == 'cea_validated']
        assert urun == [], [(b.path, b.line_no, b.matched) for b in urun]

    def test_iddia_envanteri_BUYUMEZ(self):
        """Mandal: yeni kazanılmamış iddia eklenirse KIRMIZI.

        Kilitli yedi iddianın SAHİBİ arayüz kulvarıdır (i18n anahtar
        dosyaları + şablon); bu bekçi onları onarmaz, ÇOĞALMALARINI
        engeller ve borcu ölçülebilir tutar.
        """
        simdi = {(b.path.replace(str(KOK) + '/', ''), b.rule_id, b.line_hash)
                 for b in _iddia_bulgulari()}
        yeni = simdi - KILITLI_IDDIALAR
        assert not yeni, (
            'YENİ kazanılmamış iddia girdi: %s\nHRMA↔CEA sapması ölçüldü '
            '(fakir karışımda c* −%%2,8..−%%5,9); "validated" hükmü '
            'kazanılmamıştır.' % sorted(yeni))
