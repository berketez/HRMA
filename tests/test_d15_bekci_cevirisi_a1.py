# -*- coding: utf-8 -*-
"""ÖH Dalga-15 / kulvar ``bekci-cevirisi`` — çevirilerin kalıcı bekçileri.

Bu dosya, D15/a1 aşamasında ÇEVRİLEN bekçilerin arkasındaki sözleşmeleri
kilitler. Çevrilen bekçi bir kusuru gördüğünü kanıtlamış olsa da, çeviri
sırasında kaybolabilecek üç şey vardır ve üçü de burada ayrı ayrı çivilenir:

1. ``/api/analysis/wall-profile`` fail-closed kapısı — eski bekçi boş
   gövdenin **200** dönmesini sözleşme yapıyordu; çeviri onu 422'ye çevirdi.
   Buradaki bekçi kapıyı ALAN ALAN ölçer: sekiz zorunlu girdinin her biri
   tek tek eksik ya da açık ``null`` bırakıldığında uç hüküm üretmez ve
   eksik alanı ADIYLA söyler (yokluk ⟷ null aynı hüküm).
2. Cıvata yerleşimi (defter P5B1-21) — uç bekçisinin uç vakası
   (Pc = 1000 bar) artık S3 üst-sınır kapısına takılıyor, yani o bekçi
   kusuru bir daha göremez. Buradaki bekçi kusuru ucun KABUL ETTİĞİ bandın
   tamamında arar: bandın en kötü köşesinde bile cıvatalar birbirine
   girmemeli ve yerleşim hükmü adıyla yayımlanmalı.
3. Enjektörde buhar basıncı görünürlüğü (defter D15-BEKCI-03) — çevrilen
   ayak "uyarı basılmalı" diyordu; doğrusu "uyarı K_c 1,5 altındayken
   basılmalı, üstündeyken basılmamalı ve taşıdığı K_c akışkanın KENDİ
   P_v'sinden çıkmalı"dır. İki yön de burada.

Her bekçi TERS MUTASYONLA sınandı; koşum kayıtları:
``docs/scofield/raw/OH/D15/bekci-cevirisi/a1/mutasyon.json``.
"""
import contextlib
import io
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _sessiz(fn, *args, **kwargs):
    """Modüllerin ``print`` gürültüsü bekçi çıktısını boğmasın."""
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


# ======================================================================
# 1) /api/analysis/wall-profile — fail-closed kapı, alan alan
# ======================================================================
#: Ucun uydurmayı reddettiği çekirdek girdiler. Bu liste ürün kodundan
#: ``hrma/app.py`` (``_thermal_missing_fields`` çağrısının kapı gövdesi)
#: ÖLÇÜLEREK çıkarıldı; boş gövdeye verilen 422 yanıtı da tam bu sekiz adı
#: sayıyor (betik: ``.../a1/olcum_wallprofile.py``).
WALL_PROFILE_ZORUNLU = ('chamber_pressure', 'chamber_temperature',
                        'chamber_diameter', 'chamber_length', 'burn_time',
                        'mdot_total')

#: Beyan edilmiş varsayılanı olan, yokluğu hükmü engellemeyen alanlar.
WALL_PROFILE_ISTEGE_BAGLI = {'material': 'steel', 'wall_thickness': 0.005,
                             'n_stations': 40, 'ambient_temp': 293.15,
                             'cooling_type': 'natural'}

WALL_PROFILE_TAM = {'chamber_pressure': 20, 'chamber_temperature': 3000,
                    'chamber_diameter': 0.1, 'chamber_length': 0.5,
                    'burn_time': 10, 'mdot_total': 1.0}


class TestWallProfileFailClosed:
    """P4B1-02'nin kusur tanımı: "boş gövde {} de aynı şekilde 200 dönüyor"."""

    def test_bos_govde_hukum_uretmez(self, client):
        r = client.post('/api/analysis/wall-profile', json={})
        assert r.status_code == 422, (
            f'boş gövde {r.status_code} döndü — sekiz zorunlu girdi yokken '
            'cidar profili yayımlanıyor')
        govde = r.get_json()
        assert govde.get('error') == 'incomplete_wall_profile_input'
        assert 'wall_profile' not in govde, (
            'uç hem reddediyor hem profil yayımlıyor')
        eksik = set(govde.get('missing_fields') or [])
        for alan in WALL_PROFILE_ZORUNLU:
            assert alan in eksik, (
                f'{alan} eksik listesinde yok — kullanıcı neyi vereceğini '
                f'öğrenemiyor; söylenenler: {sorted(eksik)}')

    @pytest.mark.parametrize('alan', WALL_PROFILE_ZORUNLU)
    def test_tek_alan_eksikse_hukum_yok(self, client, alan):
        yuk = {k: v for k, v in WALL_PROFILE_TAM.items() if k != alan}
        r = client.post('/api/analysis/wall-profile', json=yuk)
        assert r.status_code == 422, (
            f'{alan} verilmemişken uç {r.status_code} döndü — eksik girdi '
            'sessizce varsayıldı')
        assert 'wall_profile' not in r.get_json()

    @pytest.mark.parametrize('alan', WALL_PROFILE_ZORUNLU)
    def test_acik_null_yoklukla_ayni_hukum(self, client, alan):
        """0/None "verildi" sayılmaz: ``null`` yokluğun aynısıdır."""
        r = client.post('/api/analysis/wall-profile',
                        json=dict(WALL_PROFILE_TAM, **{alan: None}))
        assert r.status_code == 422, (
            f'{alan}=null gönderildiğinde uç {r.status_code} döndü — açık '
            'null ile yokluk ayrı yollara gidiyor')

    def test_istege_bagli_alanlar_sayiyi_kaydirmiyor(self, client):
        """Kapı eklemek hiçbir hesabı kaydırmamalı (varsayılanlar beyanlı)."""
        sade = client.post('/api/analysis/wall-profile',
                           json=dict(WALL_PROFILE_TAM))
        acik = client.post('/api/analysis/wall-profile',
                           json=dict(WALL_PROFILE_TAM,
                                     **WALL_PROFILE_ISTEGE_BAGLI))
        assert sade.status_code == acik.status_code == 200
        assert (json.dumps(sade.get_json()['wall_profile'], sort_keys=True,
                           default=str)
                == json.dumps(acik.get_json()['wall_profile'], sort_keys=True,
                              default=str)), (
            'isteğe bağlı alanlar açıkça yazılınca sayılar kaydı')


# ======================================================================
# 2) Cıvata yerleşimi — kabul edilen BANDIN tamamında (defter P5B1-21)
# ======================================================================
YAPISAL_TABAN = {'chamber_pressure': 40, 'chamber_diameter': 0.1,
                 'chamber_length': 0.5, 'throat_diameter': 0.02,
                 'burn_time': 10, 'material': 'steel_4130'}

def _band_tavani_bar():
    """Hazne basıncı üst sınırı — deponun KANONİK tablosundan.

    ÖH D17 (bekci-cevirisi a1 — defter OH-Z5-16 ŞART'ı). Bandın tavanı
    burada 500 diye YAZILMIYOR; uç kapısının okuduğu tablodan
    (``MotorDataValidator().limits``, bkz. ``hrma/app.py``
    ``_ust_sinir_bandi``) okunuyor. Tablo değişirse bandın köşeleri de
    kendiliğinden kayar ve bekçi yeni tavanı sınar.
    """
    from hrma.validation.motor_validation import MotorDataValidator
    return float(MotorDataValidator().limits['chamber_pressure']['max'])


#: Bandın tavanı [bar] — TEK kaynak (Doktrin 4).
BAND_TAVANI_BAR = _band_tavani_bar()

#: Bandın köşeleri — ölçülen en kötü oran (1,972) buradaki son satırdadır.
#: Tavan satırlarında sayı yazılmaz, ``BAND_TAVANI_BAR`` kullanılır.
CIVATA_VAKALARI = ((40, 0.4), (200, 0.4), (400, 0.4),
                   (BAND_TAVANI_BAR, 0.4), (BAND_TAVANI_BAR, 0.8),
                   (BAND_TAVANI_BAR, 1.2), (BAND_TAVANI_BAR, 2.0))


class TestCivataYerlesimiBandinIcinde:
    """P5B1-21 uç bekçisi Pc = 1000 bar'da ölçüyordu; o nokta artık 422.

    Kusur bir daha görülemeyeceği için burada kusurun YOKLUĞU bandın
    tamamında kilitleniyor: uç bir hüküm yayımlıyorsa, yayımladığı cıvata
    deseni geometrik olarak mümkün olmalı ve hükmü adıyla taşımalı.
    """

    @pytest.mark.parametrize('pc,cap', CIVATA_VAKALARI)
    def test_civatalar_birbirine_girmiyor(self, client, pc, cap):
        r = client.post('/analyze_structural_safety',
                        json=dict(YAPISAL_TABAN, chamber_pressure=pc,
                                  chamber_diameter=cap))
        assert r.status_code == 200, (
            f'Pc={pc} bar / D={cap} m bandın içinde olmalıydı, '
            f'{r.status_code} döndü')
        fas = r.get_json()['structural_analysis']['fastener_analysis']
        aralik = float(fas['bolt_spacing'])
        gerekli = float(fas['required_bolt_diameter'])
        assert aralik > gerekli, (
            f'Pc={pc}/D={cap}: cıvata aralığı {aralik:.3f} mm, gerekli çap '
            f'{gerekli:.3f} mm (oran {aralik / gerekli:.3f}) — ürün '
            'birbirine giren bir desen yayımlıyor')
        assert fas['bolt_layout_interferes'] is False

    @pytest.mark.parametrize('pc,cap', CIVATA_VAKALARI)
    def test_yerlesim_hukmu_adiyla_yayimlaniyor(self, client, pc, cap):
        """Oran, eşik ve hüküm aynı yanıtta olmalı; hüküm oranla tutarlı."""
        r = client.post('/analyze_structural_safety',
                        json=dict(YAPISAL_TABAN, chamber_pressure=pc,
                                  chamber_diameter=cap))
        fas = r.get_json()['structural_analysis']['fastener_analysis']
        for alan in ('bolt_pitch_ratio', 'bolt_min_pitch_factor',
                     'bolt_layout_ok', 'bolt_layout_interferes'):
            assert alan in fas, f'{alan} yayımlanmıyor — hüküm sessiz'
        oran = float(fas['bolt_pitch_ratio'])
        esik = float(fas['bolt_min_pitch_factor'])
        # Oran yayımlanan iki sayıdan yeniden kurulabilmeli.
        assert oran == pytest.approx(
            float(fas['bolt_spacing']) / float(fas['required_bolt_diameter']),
            rel=1e-9)
        # Hüküm oranla çelişemez.
        assert bool(fas['bolt_layout_ok']) is bool(oran >= esik), (
            f'Pc={pc}/D={cap}: oran {oran:.3f}, eşik {esik}, hüküm '
            f"{fas['bolt_layout_ok']} — hüküm sayıyla çelişiyor")

    def test_yerlesim_merdiveni_gercekten_calisiyor(self, client):
        """Onarım "hüküm basmak" değil, DESENİ DÜZELTMEK olmalı.

        PK6 onarımı yalnız bir hüküm alanı eklemedi; yerleşim kapanmadığında
        cıvata sayısını AZALTAN bir arama koydu (dolan çevre sqrt(n) ile
        büyür, az cıvata yerleşimi iyileştirir). Bu bekçi o aramanın
        gerçekten iş yaptığı bir noktayı çiviler — arama sökülürse ürün
        beyanla yetinir ve bekçi kırmızıya döner.

        ÖLÇÜLDÜ (betik ``.../a1/olcum_civata_merdiven.py``): Pc = 200 bar,
        D = 400 mm'de çap kuralı 12 cıvata seçiyor (oran 1,976 — beyan
        edilen 2,5 adımın ALTINDA); arama 6'ya iniyor ve oran 2,794 ile
        hüküm OK oluyor. Arama sökülünce aynı nokta BELOW_MINIMUM_PITCH
        verir (ters mutasyon M4).
        """
        r = client.post('/analyze_structural_safety',
                        json=dict(YAPISAL_TABAN, chamber_pressure=200,
                                  chamber_diameter=0.4))
        assert r.status_code == 200
        fas = r.get_json()['structural_analysis']['fastener_analysis']
        assert fas['bolt_count_adjusted'] is True, (
            'çap kuralının seçtiği desen yerleşimi kapatmıyordu ama sayı '
            f"düzeltilmemiş (n={fas.get('num_bolts')}, "
            f"n0={fas.get('bolt_count_initial')})")
        assert int(fas['num_bolts']) < int(fas['bolt_count_initial'])
        assert fas['bolt_layout_ok'] is True, (
            f"yerleşim kapatılabilirken kapatılmamış: oran "
            f"{fas['bolt_pitch_ratio']:.3f}, eşik "
            f"{fas['bolt_min_pitch_factor']}, durum "
            f"{fas.get('bolt_layout_status')}")

    def test_asgari_adim_esigi_tek_kaynaktan(self, client):
        """Yayımlanan eşik modülün sabitiyle aynı olmalı; kopya değil."""
        from hrma.analysis.structural_analysis import StructuralAnalyzer
        r = client.post('/analyze_structural_safety', json=dict(YAPISAL_TABAN))
        fas = r.get_json()['structural_analysis']['fastener_analysis']
        assert float(fas['bolt_min_pitch_factor']) == pytest.approx(
            float(StructuralAnalyzer._BOLT_MIN_PITCH_FACTOR), rel=1e-12), (
            'yayımlanan asgari adım çarpanı modül sabitinden ayrıştı')


# ======================================================================
# 3) Enjektör buhar basıncı görünürlüğü (defter D15-BEKCI-03)
# ======================================================================
class TestKavitasyonUyarisiPvDenBesleniyor:
    """Uyarı iki yönlü: K_c < 1,5 iken YANAR, üstünde YANMAZ.

    Eski bekçi yalnız "yanmalı" diyordu ve gerekçesi P10-A öncesi ürüne
    aitti (K_c tank istasyonundan kuruluyordu). Ölçüldü: dP = 4 bar'da
    K_c = 5,99 (uyarı GEREKMİYOR), dP = 50 bar'da K_c = 1,40 (uyarı
    GEREKİYOR). İki yön de kilitleniyor ki uyarı ne susturulabilsin ne de
    her koşulda basılsın.
    """

    P_C_BAR = 20.0
    DP_KAVITASYONLU = 50.0     # K_c ~ 1,40
    DP_GUVENLI = 4.0           # K_c ~ 5,99 (ucun kendi türettiği dP)

    def _kur(self, ox, dp):
        from hrma.utils.injector_design import InjectorDesign
        return _sessiz(InjectorDesign, mdot_ox=1.0,
                       chamber_pressure=self.P_C_BAR, oxidizer_type=ox,
                       tank_pressure=90, pressure_drop=dp,
                       oxidizer_temp=293.15)

    @staticmethod
    def _kavitasyon_uyarilari(tasarim):
        return [str(u) for u in (_sessiz(tasarim.calculate).get('warnings')
                                 or []) if 'Cavitation risk' in str(u)]

    @pytest.mark.parametrize('ox', ('n2o4', 'h2o2'))
    def test_guvenli_noktada_uyari_yok(self, ox):
        t = self._kur(ox, self.DP_GUVENLI)
        assert not self._kavitasyon_uyarilari(t), (
            f'{ox}: P_v = {t.p_vapor_bar} bar iken K_c ≈ 6; uyarı basılması '
            'P_v dışında bir sayıdan besleniyor demektir')

    @pytest.mark.parametrize('ox', ('n2o4', 'h2o2'))
    def test_kavitasyonlu_noktada_uyari_var_ve_K_c_Pv_den_cikiyor(self, ox):
        from hrma.utils.injector_design import VAPOR_PRESSURE_ASSUMED_BAR
        t = self._kur(ox, self.DP_KAVITASYONLU)
        uyarilar = self._kavitasyon_uyarilari(t)
        assert uyarilar, (
            f'{ox}: dP = {self.DP_KAVITASYONLU} bar ile K_c 1,5 altına '
            'iniyor ama uyarı basılmadı')
        eslesme = re.search(r'K_c = ([0-9.]+)', uyarilar[0])
        assert eslesme, f'{ox}: uyarı K_c sayısını taşımıyor -> {uyarilar[0]}'
        bildirilen = float(eslesme.group(1))
        beklenen = ((self.P_C_BAR + self.DP_KAVITASYONLU)
                    - VAPOR_PRESSURE_ASSUMED_BAR) / self.DP_KAVITASYONLU
        assert bildirilen == pytest.approx(beklenen, abs=0.01), (
            f'{ox}: uyarı K_c = {bildirilen}, depolanabilir P_v ile '
            f'{beklenen:.2f} olmalıydı')
        assert bildirilen < 1.5, (
            f'{ox}: uyarı yandı ama taşıdığı K_c ({bildirilen}) eşiğin '
            'üstünde — uyarı kendi sayısıyla çelişiyor')

    @pytest.mark.parametrize('ox', ('n2o4', 'h2o2'))
    def test_pv_n2o_dan_odunc_alinmiyor(self, ox):
        """Kimlik düşmesi kilidi: depolanabilir sıvı N₂O'nun 50 barını almaz."""
        from hrma.utils.injector_design import VAPOR_PRESSURE_ASSUMED_BAR
        t = self._kur(ox, self.DP_GUVENLI)
        n2o = self._kur('n2o', self.DP_GUVENLI)
        assert t.p_vapor_bar == pytest.approx(VAPOR_PRESSURE_ASSUMED_BAR,
                                              rel=1e-12)
        assert n2o.p_vapor_bar / t.p_vapor_bar > 100.0, (
            f'{ox}: buhar basıncı N₂O doyma basıncına yaklaştırıldı '
            f'({t.p_vapor_bar} ⟷ {n2o.p_vapor_bar})')


# ======================================================================
# 4) iddia_lint kayıt defteri — İKİ YÖNLÜ tazelik (defter D15-BEKCI-01)
# ======================================================================
# Kalem başlığı "taban kaydı satır numarasına dayanıyor" diyordu; ÖLÇÜM
# bunu ÇÜRÜTTÜ (betik: ``.../a1/olcum_lint_kayit.py``, çıktı
# ``once_lint_kayit.json``): kayıt anahtarı zaten satır METNİNİN
# karmasıdır ve satır kaydırma karmayı değiştirmiyor.
#
# Gerçek bayatlama iki yönlüdür ve BUGÜN yalnız biri bekçili:
#
#   ileri yön  — kayıtta OLMAYAN isabet  -> ``test_faz4_iddia_dili.py``
#                zaten kırmızı veriyor (68 isabet / 2 kayıtsız ölçüldü).
#   geri yön   — kayıtta OLUP ağaçta KARŞILIĞI KALMAYAN satır -> HİÇBİR
#                bekçi görmüyordu. Ölçüldü: tabanda 2 ölü kayıt vardı
#                (``heat_transfer_analysis.py|guaranteed|37a77871fe51``
#                sözcüğü ağaçtan tamamen kalkmıştı; ``app.py|
#                provenance_label|950969895ee9`` satır SARILINCA ölmüştü).
#                Ölü kayıt envanteri şişirir, sessizce kimseyi korumaz ve
#                sahibi olmayan bir "gerekçe"yi doğruymuş gibi taşır.
#
# Bu sınıf geri yönü çiviler; böylece her ``app.py`` birleştirmesinden
# sonra defterin İKİ yönü de aynı koşumda hükme bağlanır.
class TestIddiaLintKaydiIkiYonluTaze:

    @pytest.fixture(scope='class')
    def lint(self):
        from tools import iddia_lint
        return iddia_lint

    @pytest.fixture(scope='class')
    def tarama(self, lint):
        return _sessiz(lint.scan)

    def test_kayit_defterinde_olu_kayit_yok(self, lint, tarama):
        """Kayıttaki her satırın ağaçta CANLI bir karşılığı olmalı.

        Ölçüldü (31 Ağustos 2026, taban e88d096): 68 kayıttan 2'si ölüydü
        ve hiçbir test kırılmıyordu. Bir kaydın ölmesi iki şeyden birini
        anlatır: ya satır kaldırıldı (kayıt da kaldırılmalı), ya satır
        yeniden yazıldı/sarıldı (isabet yeniden hükme bağlanmalı). İkisi de
        insan kararıdır; sessiz kalması envanteri yalancı yapar.
        """
        canli = {(f.path, f.rule_id, f.line_hash) for f in tarama}
        baseline = lint.load_baseline()
        olu = sorted(k for k in baseline if k not in canli)
        assert not olu, (
            'iddia_lint kayıt defterinde ÖLÜ kayıt var — kayıtlı satır '
            'ağaçta bulunamıyor:\n' + '\n'.join(
                f'  {p} | {r} | {h} | {baseline[(p, r, h)][:100]}'
                for (p, r, h) in olu) +
            '\nYapılacak: satır kaldırıldıysa kaydı silin; satır '
            'değiştiyse/sarıldıysa yeni karmayla YENİDEN gerekçelendirin. '
            'Kaydı olduğu gibi bırakmak envanteri yalancı yapar.')

    def test_kayit_anahtari_satir_numarasi_degil_metin_karmasi(self, lint):
        """Anahtar satır NUMARASI olmamalı: dosya başına satır eklenince
        kayıt bayatlamamalı.

        D15-BEKCI-01'in çürütülen yarısı budur ve çürütülmüş olması onu
        bekçisiz bırakmaz: biri anahtarı satır numarasına çevirirse her
        ``app.py`` birleştirmesi defteri toptan bayatlatır.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tek = os.path.join(td, 'tek.py')
            kaydirilmis = os.path.join(td, 'kaydirilmis.py')
            iddia = 'X = "NASA-grade accurate"\n'
            with io.open(tek, 'w', encoding='utf-8') as h:
                h.write(iddia)
            with io.open(kaydirilmis, 'w', encoding='utf-8') as h:
                h.write('# yeni\n# satırlar\n' + iddia)
            a = _sessiz(lint.scan_file, tek)
            b = _sessiz(lint.scan_file, kaydirilmis)
        assert a and b, 'sentetik iddia satırı hiç yakalanmadı'
        assert a[0].line_no != b[0].line_no, 'sentetik kurulum bozuk'
        assert a[0].line_hash == b[0].line_hash, (
            'satır kaydırma kayıt anahtarını değiştirdi — anahtar satır '
            f'numarasına bağlanmış olabilir ({a[0].line_hash} != '
            f'{b[0].line_hash})')

    def test_yorum_satirlari_kural_disindan_muaf_tutulmadi(self, lint,
                                                           tarama):
        """``#`` ile başlayan satır kural dışı SAYILMAZ (ÖK-22).

        D15-BEKCI-01'in ikinci reçetesi "yorum satırlarını künye kuralından
        muaf tut"tu; ölçüm reddetti (betik
        ``.../a1/olcum_yorum_muafiyeti.py``): bugün ``#`` ile başlayan 9
        isabet var, dokuzu da kayıtta GEREKÇESİYLE duruyor — muafiyet
        dokuzunu birden envanterden düşürürdü. Üstelik ``iddia_lint``
        Markdown belgelerini de tarıyor; orada ``#`` yorum değil BAŞLIK'tır,
        yani aynı muafiyet kullanıcıya giden belge başlıklarını da kör
        ederdi.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            hedef = os.path.join(td, 'yorumlu.py')
            with io.open(hedef, 'w', encoding='utf-8') as h:
                h.write("#       basis['chamber_material_source'] = "
                        "'user_supplied'\n")
            bulgular = _sessiz(lint.scan_file, hedef)
        assert bulgular, (
            'yorum satırındaki künye iddiası artık yakalanmıyor — künye '
            'kuralına yorum muafiyeti eklenmiş olabilir (ÖK-22: sağlıklı '
            'envanter gevşetilemez)')

        diyezli = [f for f in tarama if f.line_text.lstrip().startswith('#')]
        baseline = lint.load_baseline()
        kayitsiz_diyezli = [f for f in diyezli
                            if (f.path, f.rule_id, f.line_hash) not in baseline]
        assert not kayitsiz_diyezli, (
            'yorum satırı isabetleri kayıtta gerekçesiz duruyor: ' +
            ', '.join(f'{f.path}:{f.line_no}' for f in kayitsiz_diyezli))
        assert len(diyezli) >= 9, (
            f'yorum satırı isabeti 9 ölçülmüştü, bugün {len(diyezli)} — '
            'kural kapsamı daraltılmış olabilir')
