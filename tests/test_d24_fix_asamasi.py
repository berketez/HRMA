"""ÖH Dalga-24 · FIX AŞAMASI bekçileri (çok sahipli üç kalem).

Bu üç kalem D20-D24 boyunca "kardeş dal çakışması / çok dosyalı" gerekçesiyle
kilitliydi; tek elden onarıldı. Her sınıf defterdeki BİR kalemin onarımını
kilitler. Bekçiler ters-mutasyonla sınandı: onarım baytları geçici geri
yazıldığında ilgili test KIRMIZI olur
(kanıt: docs/scofield/raw/OH/D24/fix_asamasi/mutasyon.json).

Ölçüm dosyaları: docs/scofield/raw/OH/D24/fix_asamasi/once.json (taban
2e4d81f) ve sonra.json (bu ağaç).
"""

import ast
import contextlib
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAKET = ROOT / 'hrma'


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


# ---------------------------------------------------------------------------
# P10B3-10 — g_0 / R_universal satır-içi literalleri
# ---------------------------------------------------------------------------

#: Kütlesel yerçekimi sabitinin AYIRT EDİCİ yazımları. Çıplak ``9.8``
#: BİLEREK dışarıda: o sayı ölçüde yaygın (ÖLÇÜLDÜ — hrma/ içindeki iki
#: örneği de Inconel 625'in ısı iletkenliğidir, k = 9,8 W/m/K, kaynak
#: Special Metals 625 veri sayfası; materials_db.py :637 ve :650). D22'nin
#: "materials_db 9,8" iddiası bu yüzden ÇÜRÜTÜLDÜ: orada yerçekimi yok.
G0_LITERALLERI = {9.80665, 9.81, 9.8066, 9.807, 9.80663}

#: Evrensel gaz sabitinin kmol ve mol tabanlı yazımları.
R_LITERALLERI = {
    8314.462618, 8314.46, 8314.5, 8314.0, 8314.462, 8314.4621, 8314.472,
    8.314462618, 8.314,
}

#: Sabitin TANIMLANDIĞI yer + tanımın kendisiyle aynı sayıyı taşıması
#: meşru olan dosyalar. constants.py tek tanım noktasıdır; ICAO R* ise
#: AYRI bir standardın (ICAO 1993) tanım sayısıdır, CODATA ile
#: değiştirilmesi atmosfer tablolarını bozar.
SABIT_TANIM_DOSYALARI = {'hrma/constants.py'}


def _sayisal_literaller(yol):
    """Dosyadaki sayısal ast.Constant düğümleri — yorum/docstring HARİÇ."""
    agac = ast.parse(yol.read_text(encoding='utf-8'), filename=str(yol))
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Constant):
            continue
        deger = dugum.value
        if isinstance(deger, bool) or not isinstance(deger, (int, float)):
            continue
        yield dugum.lineno, float(deger)


def _paket_dosyalari():
    for yol in sorted(PAKET.rglob('*.py')):
        if '__pycache__' in yol.parts:
            continue
        if str(yol.relative_to(ROOT)) in SABIT_TANIM_DOSYALARI:
            continue
        yield yol


class TestP10B310SabitTekKaynak:
    """``hrma/constants.py`` "magic-number tutarsızlıkları bu modül üzerinden
    önlenir" diyordu ama ÖLÇÜLDÜ (once.json K1, taban 2e4d81f): g_0 ve
    R_universal literalleri modül DIŞINDA 13 kez satır içindeydi —
    hybrid_rocket_engine 3× (8 314,462618), external_data_fetcher 4×
    (8 314,5), chemical_database 3× (8,314), app.py 1× (9,80665) ve
    materials_db 2× (9,8, ÇÜRÜTÜLDÜ: ısı iletkenliği).

    Sayısal sonuç: iki yaprak DEĞİŞTİ ve beyan edildi —
    ``gas_constant`` -4,4960e-6 bağıl (8 314,5 -> 8 314,462618),
    ``cp/enthalpy/entropy`` +5,5644e-5 bağıl (8,314 -> 8,314462618).
    """

    def test_g0_literali_kalmadi(self):
        bulgular = []
        for yol in _paket_dosyalari():
            for satir, deger in _sayisal_literaller(yol):
                if deger in G0_LITERALLERI:
                    bulgular.append(
                        f'{yol.relative_to(ROOT)}:{satir} -> {deger!r}')
        assert not bulgular, (
            'g_0 satır-içi literal olarak yazılmış; hrma.constants.G_0 '
            'ithal edilmeli (tek kaynak): ' + '; '.join(bulgular))

    def test_r_universal_literali_kalmadi(self):
        bulgular = []
        for yol in _paket_dosyalari():
            for satir, deger in _sayisal_literaller(yol):
                if deger in R_LITERALLERI:
                    bulgular.append(
                        f'{yol.relative_to(ROOT)}:{satir} -> {deger!r}')
        assert not bulgular, (
            'R_universal satır-içi literal olarak yazılmış; '
            'hrma.constants.R_UNIVERSAL (kmol) ya da R_MOLAR (mol) ithal '
            'edilmeli: ' + '; '.join(bulgular))

    def test_mol_tabani_kmol_tabanindan_turetilir(self):
        """R_MOLAR ayrı yazılmış bir sayı DEĞİL, R_UNIVERSAL/1000 olmalı.

        İkisi ayrı yazılırsa ileride biri güncellenip diğeri kalır — bu
        kalemin kökündeki hatanın ta kendisi.
        """
        from hrma import constants
        assert constants.R_MOLAR == constants.R_UNIVERSAL / 1000.0
        # ICAO R* AYRI bir standardın tanımıdır, R_MOLAR ile karışmamalı.
        assert constants.R_STAR_ICAO != constants.R_MOLAR

    def test_tuketiciler_tek_kaynagi_okuyor(self):
        """Onarılan dört dosya sabiti gerçekten constants'tan ithal ediyor."""
        beklenen = {
            'hrma/app.py': 'G_0',
            'hrma/engines/hybrid_rocket_engine.py': 'R_UNIVERSAL',
            'hrma/data/external_data_fetcher.py': 'R_UNIVERSAL',
            'hrma/data/chemical_database.py': 'R_MOLAR',
        }
        for goreli, ad in beklenen.items():
            agac = ast.parse((ROOT / goreli).read_text(encoding='utf-8'))
            ithal_edildi = any(
                isinstance(d, ast.ImportFrom)
                and (d.module or '').endswith('constants')
                and any(a.name == ad for a in d.names)
                for d in ast.walk(agac))
            assert ithal_edildi, (
                f'{goreli} sabiti {ad} adıyla hrma.constants\'tan ithal '
                'etmiyor (tek kaynak kuralı)')

    def test_inconel_625_iletkenligi_yercekimi_degil(self):
        """ÇÜRÜTME KİLİDİ: materials_db'deki 9,8 ısı iletkenliğidir.

        Bu test, ileride birinin "9,8 de g_0'dır" deyip Inconel 625'in
        k değerini 9,80665'e çevirmesini engeller.
        """
        from hrma.data.materials_db import get_material
        mat = get_material('inconel_625')
        assert mat['thermal_conductivity'] == 9.8
        assert mat['k_curve'][294] == 9.8


# ---------------------------------------------------------------------------
# P15B1-05 — iki termokimya ağacı: çalışma noktası beyanı + birim tuzağı
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def hibrit_govde():
    """Tek bir /calculate koşumu — bu bölümün tüm testleri onu paylaşır."""
    from hrma.app import app
    app.config['TESTING'] = True
    istemci = app.test_client()
    yanit = _sessiz(istemci.post, '/calculate', json={
        'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
        'chamber_pressure': 20.0, 'fuel_type': 'htpb',
        'oxidizer_type': 'n2o'})
    assert yanit.status_code == 200
    govde = yanit.get_json()
    return govde.get('motor', govde)


def _sayisal_yapraklar(dugum, on='', cik=None):
    cik = {} if cik is None else cik
    if isinstance(dugum, dict):
        for k, v in dugum.items():
            _sayisal_yapraklar(v, f'{on}.{k}' if on else str(k), cik)
    elif isinstance(dugum, (list, tuple)):
        for i, v in enumerate(dugum[:2]):
            _sayisal_yapraklar(v, f'{on}[{i}]', cik)
    elif isinstance(dugum, bool) or dugum is None:
        pass
    elif isinstance(dugum, (int, float)):
        cik[on] = float(dugum)
    return cik


class TestP15B105IkiTermokimyaAgaci:
    """Hibrit yanıtı aynı iskeleti iki ağaçta yayımlıyor ve ÖLÇÜLDÜ
    (once.json K2, taban 2e4d81f): 271 ortak yolun 146'sı >%1, 43'ü >%10
    ayrışıyor; sebep tek yaprakta (``inputs.of_ratio`` 6,0 ⟷ 6,0785641).

    Ayrışma MEŞRUDUR (tasarım noktası ⟷ danışma optimum noktası) ama
    İLAN EDİLMİYORDU. Bu bekçi ilanı kilitler; ayrıca aynı yanıtta aynı
    adın iki ayrı birimde (1000×) yayımlanmasını yasaklar.
    """

    def test_iki_agac_calisma_noktasini_ILAN_ediyor(self, hibrit_govde):
        from hrma.engines import combustion_analysis as ca
        tasarim = hibrit_govde['combustion_analysis']['inputs']
        optimum = hibrit_govde['optimum_analysis']['analysis']['inputs']

        assert tasarim['operating_point'] == ca.OPERATING_POINT_DESIGN
        assert optimum['operating_point'] == ca.OPERATING_POINT_OPTIMUM_SEARCH
        # Gerekçe metni de yayımlanır (ad tek başına yetmez).
        assert tasarim['operating_point_basis']
        assert 'ADVISORY' in optimum['operating_point_basis']

    def test_ayrisan_agaclarin_of_orani_gercekten_farkli(self, hibrit_govde):
        """Beyan süs değil: iki ağaç GERÇEKTEN farklı noktada durmalı.

        Eğer bir gün ikisi aynı O/F'ye bağlanırsa (ki bu optimum aramasını
        yok eder) bu test kırmızı olur ve kararın bilinçli alınmasını
        zorlar.
        """
        tasarim_of = hibrit_govde['combustion_analysis']['inputs']['of_ratio']
        optimum_of = (hibrit_govde['optimum_analysis']['analysis']
                      ['inputs']['of_ratio'])
        assert tasarim_of == pytest.approx(6.0)
        assert optimum_of != pytest.approx(tasarim_of, rel=1e-9), (
            'optimum ağacı tasarım noktasına çökmüş: danışma araması '
            'bilgi taşımıyor')
        # Tasarım ağacı kullanıcının istediği O/F'de KALMALI.
        assert hibrit_govde['of_ratio'] == pytest.approx(tasarim_of)

    def test_ayni_ad_IKI_BIRIMDE_yayimlanmiyor(self, hibrit_govde):
        """1000× tuzağı: ``enthalpy``/``entropy``/``cp``/``cv``.

        ÖLÇÜLDÜ (once.json K2): ``compositions.chamber.enthalpy`` =
        1 605 035,22 J/kg iken ``...stations.chamber.enthalpy`` =
        1 605,0352 kJ/kg — aynı ad, tam 1000 kat. İstasyon tablosunun
        adları artık birimi taşıyor.
        """
        nums = _sayisal_yapraklar(hibrit_govde)
        for ad in ('enthalpy', 'entropy', 'cp', 'cv'):
            yollar = [k for k in nums if k.endswith('.' + ad)]
            istasyon = [k for k in yollar if '.stations.' in k]
            assert not istasyon, (
                f"'{ad}' istasyon tablosunda birimsiz adla yayımlanıyor "
                f'(1000× tuzağı geri geldi): {istasyon}')

    def test_istasyon_alanlari_birimi_ADINDA_tasiyor(self, hibrit_govde):
        istasyon = (hibrit_govde['combustion_analysis']['performance']
                    ['thermodynamic_properties']['stations']['chamber'])
        for ad in ('enthalpy_kJ_kg', 'entropy_kJ_kg_K', 'cp_kJ_kg_K',
                   'cv_kJ_kg_K', 'gibbs_energy_kJ_kg'):
            assert ad in istasyon, ad
        # Eski birimsiz adlar GERİ GELMEMELİ (iki ad yayımlamak tuzağı
        # sürdürürdü — tek ad + sürüm notu kuralı).
        for eski in ('enthalpy', 'entropy', 'cp', 'cv', 'gibbs_energy'):
            assert eski not in istasyon, (
                f"eski birimsiz ad '{eski}' geri gelmiş")

    def test_birim_sozlukleri_govdede_ve_TEK_KAYNAK(self, hibrit_govde):
        from hrma.engines import combustion_analysis as ca
        termo = (hibrit_govde['combustion_analysis']['performance']
                 ['thermodynamic_properties'])
        assert termo['station_units'] == ca._STATION_UNITS
        assert (hibrit_govde['combustion_analysis']['composition_units']
                == ca._COMPOSITION_UNITS)
        # Birim sözlüğü istasyon alanlarının TAMAMINI kapsamalı.
        assert set(termo['stations']['chamber']) == set(termo['station_units'])

    def test_1000_kat_iliskisi_KORUNDU(self, hibrit_govde):
        """Sayılar değişmedi: yalnız adlar birimlendi.

        İstasyon (kJ) ile bileşim (J) arasındaki 1000 kat ilişkisi hâlâ
        geçerli olmalı — ad değişimi bir birim DÖNÜŞÜMÜ değildi.
        """
        ca_agac = hibrit_govde['combustion_analysis']
        for ist in ('chamber', 'throat', 'exit'):
            j = ca_agac['compositions'][ist]
            kj = (ca_agac['performance']['thermodynamic_properties']
                  ['stations'][ist])
            assert kj['cp_kJ_kg_K'] == pytest.approx(j['cp'] / 1000.0,
                                                     rel=1e-12)
            assert kj['entropy_kJ_kg_K'] == pytest.approx(
                j['entropy'] / 1000.0, rel=1e-12)

    def test_bilinmeyen_calisma_noktasi_REDDEDILIR(self):
        """Beyan alanının kendisi uydurma taşıyamaz (fail-closed)."""
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        cozumleyici = CombustionAnalyzer()
        with pytest.raises(ValueError, match='operating_point'):
            _sessiz(cozumleyici.analyze_combustion,
                    {'C4H6': 100.0}, 'n2o', 6.0, 20.0,
                    operating_point='uydurma_nokta')


# ---------------------------------------------------------------------------
# OH-D23-03 — 'aluminum_6061' varsayılanı: tek kaynak + sessizlik yasağı
# ---------------------------------------------------------------------------

JS_KOK = PAKET / 'static' / 'js'


class TestOHD2303VarsayilanMalzeme:
    """ÖLÇÜLDÜ (once.json K3, taban 2e4d81f): ``/api/pressure-vessel-analysis``
    ``material`` gönderilmeyen gövde ile açıkça ``'aluminum_6061'`` gönderen
    gövde için BİT-AYNI yanıt üretiyordu (``ayirt_edilebilir`` = False) ve
    ``defaults_applied`` alanı YOKTU — alüminyum bir seçim değil, sessiz bir
    kabuldü; oysa malzeme kimliği MAWP/burst/derating zincirini belirliyor.

    Defterin "33 satır-içi varsayılan" ifadesi KISMEN ÇÜRÜTÜLDÜ: 41 geçişin
    çoğu açılır liste seçeneği, takma ad tablosu, i18n etiketi ya da
    yorumdur (aşağıda sayılarak gösterilir).
    """

    def test_varsayilan_TEK_KAYNAKTA(self):
        from hrma.data import materials_db
        assert materials_db.DEFAULT_STRUCTURAL_MATERIAL in materials_db.MATERIALS

    def test_kap_ucu_varsayilani_SESSIZ_uygulamiyor(self):
        from hrma.app import app
        from hrma.data.materials_db import DEFAULT_STRUCTURAL_MATERIAL
        app.config['TESTING'] = True
        istemci = app.test_client()
        yuk = {'meop_bar': 50.0, 'inner_diameter_mm': 200.0}

        yoksa = _sessiz(istemci.post, '/api/pressure-vessel-analysis',
                        json=yuk).get_json()
        varsa = _sessiz(istemci.post, '/api/pressure-vessel-analysis',
                        json=dict(yuk, material=DEFAULT_STRUCTURAL_MATERIAL)
                        ).get_json()

        # Varsayılan uygulandıysa ADIYLA beyan edilir (ÖK-19).
        kunye = yoksa['defaults_applied']
        assert [k['field'] for k in kunye] == ['material']
        assert kunye[0]['value'] == DEFAULT_STRUCTURAL_MATERIAL
        assert kunye[0]['reason'] == 'not_supplied'
        # Kullanıcı verdiyse künye BOŞ — beyan "her zaman dolu" değil.
        assert varsa['defaults_applied'] == []
        # İki gövde artık AYIRT EDİLEBİLİR (ölçümdeki kusur buydu).
        assert json.dumps(yoksa, sort_keys=True, default=str) != \
            json.dumps(varsa, sort_keys=True, default=str)

    def test_beyan_disinda_SAYI_DEGISMEDI(self):
        """Onarım bir davranış değişikliği değil: aynı varsayılan, aynı sonuç.

        ``defaults_applied`` çıkarıldığında iki gövde bit-aynı kalmalı.
        """
        from hrma.app import app
        from hrma.data.materials_db import DEFAULT_STRUCTURAL_MATERIAL
        app.config['TESTING'] = True
        istemci = app.test_client()
        yuk = {'meop_bar': 50.0, 'inner_diameter_mm': 200.0}
        a = _sessiz(istemci.post, '/api/pressure-vessel-analysis',
                    json=yuk).get_json()
        b = _sessiz(istemci.post, '/api/pressure-vessel-analysis',
                    json=dict(yuk, material=DEFAULT_STRUCTURAL_MATERIAL)
                    ).get_json()
        a.pop('defaults_applied'), b.pop('defaults_applied')
        assert json.dumps(a, sort_keys=True, default=str) == \
            json.dumps(b, sort_keys=True, default=str)

    def test_uc_satir_ici_varsayilan_TASIMIYOR(self):
        """``app.py`` kap ucu artık kendi varsayılanını yazmıyor."""
        kaynak = (ROOT / 'hrma/app.py').read_text(encoding='utf-8')
        assert "data.get('material', 'aluminum_6061')" not in kaynak

    def test_sunucu_istemci_IKIZI_esit(self):
        """JS ikizi sunucunun ilan ettiği değerle AYNI olmalı.

        Paneller formu senkron kurduğu için istemcinin bir başlangıç değeri
        taşıması zorunlu; ikiz TEK yerde (materials_catalog.js) durur ve bu
        bekçi onu sunucuyla eşitler.
        """
        from hrma.app import app
        from hrma.data.materials_db import DEFAULT_STRUCTURAL_MATERIAL
        app.config['TESTING'] = True
        katalog = _sessiz(app.test_client().get, '/api/materials').get_json()
        assert katalog['default_structural_material'] == \
            DEFAULT_STRUCTURAL_MATERIAL

        js = (JS_KOK / 'materials_catalog.js').read_text(encoding='utf-8')
        import re
        m = re.search(
            r"var DEFAULT_STRUCTURAL_MATERIAL\s*=\s*'([^']+)'", js)
        assert m, 'materials_catalog.js ikiz sabiti bulunamadı'
        assert m.group(1) == DEFAULT_STRUCTURAL_MATERIAL, (
            'istemci ikizi sunucudan ayrışmış: %s ⟷ %s'
            % (m.group(1), DEFAULT_STRUCTURAL_MATERIAL))

    def test_panel_IKIZLERI_sunucuyla_esit(self):
        """Panel ikizleri sunucudan AYRIŞAMAZ.

        Paneller formu senkron kurar ve ``materials_catalog.js``
        yüklenmemişse son çare bir ikiz sabite düşer (cıvatalı bağlantı ucu
        ``member_material``'ı ZORUNLU tuttuğu için boş bırakmak 400 verirdi).
        İkiz YASAK DEĞİL, AYRIŞMA yasak: burada hepsi sunucunun tek
        kaynağıyla eşitlenir.

        Ayrıca panel dosyası form alanına DOĞRUDAN dizgi yazamaz — değer
        yalnız ``VARSAYILAN_MALZEME`` değişkeni üzerinden geçmeli.
        """
        import re
        from hrma.data.materials_db import DEFAULT_STRUCTURAL_MATERIAL
        ikiz_sayisi = 0
        for yol in sorted((JS_KOK / 'panels').glob('*.js')):
            metin = yol.read_text(encoding='utf-8')
            for no, satir in enumerate(metin.splitlines(), 1):
                if 'aluminum_6061' not in satir:
                    continue
                # Açılır liste SEÇENEĞİ meşrudur: ['aluminum_6061', 'Aluminum ...']
                if "'Aluminum 6061" in satir:
                    continue
                # Kalan tek meşru biçim: ikiz son-çare ataması.
                m = re.search(r": '([a-z0-9_]+)';\s*/\* ikiz", satir)
                assert m, (
                    f'{yol.name}:{no} varsayılan malzemeyi doğrudan yazıyor; '
                    'form alanı VARSAYILAN_MALZEME üzerinden okumalı')
                assert m.group(1) == DEFAULT_STRUCTURAL_MATERIAL, (
                    f'{yol.name}:{no} ikizi sunucudan ayrışmış: '
                    f'{m.group(1)} ⟷ {DEFAULT_STRUCTURAL_MATERIAL}')
                ikiz_sayisi += 1
        # İkizler gerçekten var; test boş kümeyi "geçti" saymasın.
        assert ikiz_sayisi >= 2, ikiz_sayisi

    def test_panel_kunyeyi_CANLI_dalda_basiyor(self):
        """Beyanı basan dal ÖLÜ olamaz.

        ``test_wave3_contract`` ters-yön sözleşmesi panel dosyasında alan
        ADININ geçmesini arar; ölçüldü (mutasyon M6) ki bu METİN eşleşmesidir
        ve ``if (false && Array.isArray(d.defaults_applied))`` mutasyonunu
        YAKALAMAZ — dizgi hâlâ dosyada durur. Beyanı basmayan panel, beyanı
        olmayan panelle aynıdır; bu yüzden koşulun canlı biçimi burada
        birebir kilitlenir.
        """
        metin = (JS_KOK / 'panels' / 'vessel_panel.js').read_text(
            encoding='utf-8')
        assert 'if (Array.isArray(d.defaults_applied)) {' in metin, (
            'vessel_panel.js varsayılan künyesini canlı bir dalda basmıyor '
            '(koşul değişmiş ya da ölü hâle getirilmiş)')
        # Künye gerçekten listeye basılmalı (yalnız koşul yetmez).
        assert 'd.defaults_applied.map(' in metin

    def test_33_iddiasi_OLCULEREK_ayristirildi(self):
        """ÇÜRÜTME KİLİDİ: geçişlerin çoğu varsayılan DEĞİL.

        Sayım bozulursa (biri gerçek bir varsayılan eklerse) test kırmızı
        olur ve iddianın yeniden ölçülmesini zorlar.
        """
        import re
        sayim = {'secenek_listesi': 0, 'takma_ad': 0, 'i18n': 0, 'diger': 0}
        for yol in sorted(PAKET.rglob('*')):
            if yol.suffix not in ('.js', '.html', '.py') or not yol.is_file():
                continue
            if '__pycache__' in yol.parts:
                continue
            for satir in yol.read_text(encoding='utf-8').splitlines():
                if 'aluminum_6061' not in satir:
                    continue
                s = satir.strip()
                if "'Aluminum 6061" in s or '<option' in s:
                    sayim['secenek_listesi'] += 1
                elif re.search(r"'[^']+'\s*:\s*'aluminum_6061'", s):
                    sayim['takma_ad'] += 1
                elif 'i18n' in yol.name or 'data-i18n' in s:
                    sayim['i18n'] += 1
                else:
                    sayim['diger'] += 1
        # Seçenek/takma ad/i18n toplamı, "varsayılan" sayılamayacak
        # geçişlerdir ve çoğunluğu oluşturur.
        varsayilan_olmayan = (sayim['secenek_listesi'] + sayim['takma_ad']
                              + sayim['i18n'])
        assert varsayilan_olmayan >= 12, sayim
