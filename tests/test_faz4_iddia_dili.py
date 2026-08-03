"""Faz 4B — iddia dili ve standart atfı bekçileri (C1-C5 + H4).

Kapattıkları somut kusurlar (hepsi HEAD ``a7ff1e7`` üzerinde ölçüldü,
2 Ağustos 2026; kayıt: ``docs/FAZ4_CODEX_TEYIT.md`` §C):

* **C1** — ``pdf_generator.py:992`` teknik ekte "This analysis employs
  NASA-standard methodologies for rocket motor performance evaluation"
  basıyordu; boş ``analysis_results`` ile bile. 2026-07-28'de yapılan
  PDF-NASA-4 düzeltmesi yalnız kapağa ve yönetici özetine uygulanmış,
  teknik ek atlanmıştı — ve ``:274`` teknik eki ``'technical'`` rapor
  tipinde gerçekten çağırıyor, yani ölü kod DEĞİLDİ.
* **C1b** — bekçi testi (``test_safety_honesty.py:200``) yalnız
  ``'conducted using NASA-standard methodologies'`` DİZESİNİ arıyordu;
  ``:992``'deki ``'employs NASA-standard methodologies'`` varyantı
  yakalanmadığı için test yeşil kalıyordu. Artık desen aranır.
* **C2** — NASA-STD-5012 iki katmanlı yanlış atıf: (1) her yerde
  "Pressure Vessels & Pressurized Systems" başlığıyla anılıyordu —
  gerçek adı *Strength and Life Assessment Requirements for
  Liquid-Fueled Space Propulsion System Engines* (Rev. B, 2016);
  (2) lülede izantropik Mach-alan bağıntısının ve besleme hattı basınç
  düşümünün KAYNAĞI olarak gösteriliyordu. Bir mukavemet/ömür standardı
  gaz dinamiği bağıntısının kaynağı olamaz.
* **C3** — NASA SP-8124 "Thermal Design Criteria" diye anılıyordu;
  gerçek adı *Liquid Rocket Engine Self-Cooled Combustion Chambers*
  (1977, NTRS 78N21211).
* **C4** — ``nasa_realtime_validator.py:284-292`` TEK bir yüzde
  hatasından üç yasak hüküm üretiyordu: "NASA-grade accurate", "Good
  accuracy for engineering purposes", "Acceptable for preliminary
  design".
* **C5** — ``formulas.html:1164-1165`` §14 "Professional-grade analysis
  methods based on validated NASA standards" diyordu.
* **H4** — kodda 40 farklı standart atfı var; kontrol edilen üç başlığın
  üçü de yanlıştı. ``tools/iddia_lint.py`` + ``docs/STANDART_ATIFLARI.md``
  bunu makinece denetlenir hale getirir.

Testler kaynak METNİ okur: iddia dili çalışma zamanında değil, kaynakta
üretilir; bir sonraki kişinin geri koyması da kaynakta olur.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools import iddia_lint  # noqa: E402


def _read(rel_path: str) -> str:
    with open(os.path.join(REPO_ROOT, rel_path), encoding='utf-8') as handle:
        return handle.read()


def _read_flat(rel_path: str) -> str:
    """Satır sonlarını boşluğa indirger.

    Kaynak dosyalarda uzun standart adları satır sonuna sarılıyor (ör.
    performance_panel.js yorumunda "Strength\\n   and Life Assessment ...").
    Ham metinde alt dize araması bu yüzden yanlış negatif verir.
    """
    return ' '.join(_read(rel_path).split())


def _read_without_exempt(rel_path: str) -> str:
    """Muafiyet işaretli satırları atarak okur.

    Düzeltme yorumları kaldırdıkları kusuru birebir alıntılamak zorunda;
    bu alıntılar ``IDDIA-LINT-MUAF`` / ``...-BASLANGIC``-``...-BITIS`` ile
    işaretlidir ve kusurun kendisi sayılmaz.
    """
    kept = []
    exempt_block = False
    for line in _read(rel_path).splitlines():
        if iddia_lint.BLOCK_OPEN in line:
            exempt_block = True
            continue
        if iddia_lint.BLOCK_CLOSE in line:
            exempt_block = False
            continue
        if exempt_block or iddia_lint.INLINE_EXEMPT in line:
            continue
        kept.append(line)
    return '\n'.join(kept)


# ---------------------------------------------------------------------------
# H4a — lint aracının kendisi
# ---------------------------------------------------------------------------
class TestLintAraci:
    """Araç çalışmazsa geri kalan bütün bekçiler kâğıt üstünde kalır."""

    def test_hrma_agacinda_kayitsiz_iddia_yok(self):
        findings = iddia_lint.scan()
        baseline = iddia_lint.load_baseline()
        new_hits = iddia_lint.unbaselined(findings, baseline)
        assert not new_hits, '\n'.join(
            f'{f.path}:{f.line_no} [{f.rule_id}] {f.line_text[:120]}'
            for f in new_hits)

    def test_kullaniciya_giden_belgeler_de_taraniyor(self):
        """H5-5 (Faz 5): araç belgeleri HİÇ taramıyordu.

        Ölçüm (3 Ağustos 2026, HEAD 9d3728e): ``DEFAULT_SCAN_ROOT = hrma/``
        ve ``SCANNED_SUFFIXES = ('.py', '.js', '.html')`` idi; yani
        ``README.md``, ``docs/USER_MANUAL.md``, ``docs/user_guide/*.tex`` ve
        sürüm notları taranmıyordu. Aynı kurallar belgelere uygulanınca beş
        satırda hâlâ "digital twin" yazdığı görüldü — oysa
        ``packaging/release_notes_v2.6.1.md:47`` bu ifadenin "throughout"
        değiştirildiğini söylüyordu. Ayrıca ``hrma/app.py:786``
        (``/user-guide/open``) ``docs/user_guide`` içeriğini doğrudan
        kullanıcıya açıyor.
        """
        assert {'.md', '.tex'} <= set(iddia_lint.SCANNED_SUFFIXES), (
            f'belge uzantıları taranmıyor: {iddia_lint.SCANNED_SUFFIXES}')

        hedefler = set(iddia_lint.DEFAULT_SCAN_TARGETS)
        for zorunlu in ('hrma', 'README.md', 'docs/USER_MANUAL.md',
                        'docs/user_guide'):
            assert zorunlu in hedefler, (
                f'{zorunlu} varsayılan tarama hedeflerinde yok: '
                f'{sorted(hedefler)}')

        # Tarama gerçekten belge dosyalarına DOKUNUYOR mu (yol listesi boş
        # kalmasın diye kanıt: en az bir .md kayıtlı isabet üretiyor).
        yollar = {f.path for f in iddia_lint.scan()}
        assert any(y.endswith('.md') for y in yollar), (
            'hiçbir .md dosyası taranmamış — hedef listesi çalışmıyor')

    def test_digital_twin_ifadesi_belgelerden_kalkti(self):
        """H5-5: v2.6.1'in "throughout" iddiası artık gerçekten doğru.

        Tarihsel sürüm notları (``packaging/release_notes_v2.5.1.md``,
        ``v2.6.1.md``) hariç tutulur: onlar kaldırılan ifadeyi ALINTILAR ve
        geriye dönük değiştirilmez; kayıt defterinde gerekçeleriyle durur.
        """
        canli = [f for f in iddia_lint.scan()
                 if f.rule_id == 'digital_twin'
                 and not f.path.startswith('packaging/release_notes_')]
        assert not canli, '\n'.join(
            f'{f.path}:{f.line_no} {f.line_text[:120]}' for f in canli)

    def test_baseline_her_kaydin_gerekcesi_var(self):
        baseline = iddia_lint.load_baseline()
        assert baseline, 'kayıt defteri boş — dosya bulunamamış olabilir'
        gerekcesiz = [key for key, reason in baseline.items()
                      if len(reason.strip()) < 10]
        assert not gerekcesiz, gerekcesiz

    def test_acik_borclar_gorunur_kaliyor(self):
        """Kayıt defteri susturma listesi değil; borçlar sayılabilmeli.

        2 Ağustos 2026: defter kurulduğunda 10 AÇIK BORÇ vardı ve bu test
        "hiç kalmadıysa" durumunu kabul etmiyordu — amacı defterin sessizce
        boşaltılmasını engellemekti. Borçların onu da aynı gün kapandı, o
        yüzden test SAYIYA değil NİYETE bağlandı: borç kalmadıysa bunun
        nedeni defterde AÇIKÇA yazılı olmalı. Böylece "borç yok" ile
        "borçlar silindi" birbirine karışmaz.
        """
        baseline = iddia_lint.load_baseline()
        assert baseline, 'kayıt defteri tamamen boş — envanter kayboldu'
        debts = iddia_lint.open_debts(baseline)
        for _path, _rule, _digest, reason in debts:
            assert iddia_lint.DEBT_MARKER in reason
        if not debts:
            with open(iddia_lint.BASELINE_PATH, encoding='utf-8') as handle:
                metin = handle.read()
            assert 'AYIKLANDI' in metin, (
                'AÇIK BORÇ kaydı kalmamış ama defterde bunun gerekçesi yok; '
                'borçlar sessizce silinmiş olabilir')

    @pytest.mark.parametrize('phrase', [
        'NASA-grade accurate',
        'validated NASA standards',
        'NASA-standard methodologies',
        'Professional-grade analysis',
        'Acceptable for preliminary design',
        'flight certified hardware',
        'ready for manufacturing',
        'MOTOR SAFE FOR OPERATION',
        'a digital twin of the engine',
        'NFPA-compliant design',
    ])
    def test_yasak_ifadeler_yakalaniyor(self, phrase, tmp_path):
        target = tmp_path / 'ornek.py'
        target.write_text(f'# {phrase}\n', encoding='utf-8')
        assert iddia_lint.scan_file(str(target)), phrase

    def test_satir_ici_muafiyet_calisiyor(self, tmp_path):
        target = tmp_path / 'ornek.py'
        target.write_text(
            '# eski kod "NASA-grade accurate" diyordu  IDDIA-LINT-MUAF\n',
            encoding='utf-8')
        assert not iddia_lint.scan_file(str(target))

    def test_blok_muafiyeti_calisiyor(self, tmp_path):
        target = tmp_path / 'ornek.py'
        target.write_text(
            '"""IDDIA-LINT-MUAF-BASLANGIC\n'
            '    "Calculation is NASA-grade accurate"\n'
            '    "Acceptable for preliminary design"\n'
            'IDDIA-LINT-MUAF-BITIS\n'
            '"""\n', encoding='utf-8')
        assert not iddia_lint.scan_file(str(target))

    def test_blok_kapaninca_muafiyet_biter(self, tmp_path):
        target = tmp_path / 'ornek.py'
        target.write_text(
            '# IDDIA-LINT-MUAF-BASLANGIC\n'
            '# "NASA-grade accurate"\n'
            '# IDDIA-LINT-MUAF-BITIS\n'
            'NOTE = "Calculation is NASA-grade accurate"\n', encoding='utf-8')
        hits = iddia_lint.scan_file(str(target))
        assert len(hits) == 1 and hits[0].line_no == 4

    def test_olumsuzlanmis_garanti_isabet_saymaz(self, tmp_path):
        """"NOT guaranteed" bir iddia değil, sınır beyanıdır."""
        target = tmp_path / 'ornek.py'
        target.write_text(
            '# the Joukowsky peak is NOT guaranteed to be the upper bound\n',
            encoding='utf-8')
        assert not iddia_lint.scan_file(str(target))

    def test_yanlis_standart_basliklari_yakalaniyor(self, tmp_path):
        target = tmp_path / 'ornek.py'
        target.write_text(
            "REF1 = 'NASA-STD-5012 Pressure Vessels & Pressurized Systems'\n"
            "REF2 = 'NASA SP-8124 Thermal Design Criteria'\n"
            "REF3 = 'NASA SP-125 Liquid-Propellant Rocket Engine Performance'\n",
            encoding='utf-8')
        rules = {f.rule_id for f in iddia_lint.scan_file(str(target))}
        assert rules == {'std5012_wrong_title', 'sp8124_wrong_title',
                         'sp125_wrong_title'}

    def test_kayit_anahtari_satir_numarasindan_bagimsiz(self, tmp_path):
        """Dosyanın başına satır eklenince kayıt bayatlamamalı."""
        first = tmp_path / 'a.py'
        first.write_text('X = "NASA-grade accurate"\n', encoding='utf-8')
        second = tmp_path / 'b.py'
        second.write_text('# yeni yorum\n# ikinci\n'
                          'X = "NASA-grade accurate"\n', encoding='utf-8')
        assert (iddia_lint.scan_file(str(first))[0].line_hash
                == iddia_lint.scan_file(str(second))[0].line_hash)


# ---------------------------------------------------------------------------
# H4b — standart atıfları kayıt defteri
# ---------------------------------------------------------------------------
class TestStandartKayitDefteri:

    @pytest.fixture(scope='class')
    def defter(self):
        return _read('docs/STANDART_ATIFLARI.md')

    @pytest.mark.parametrize('numara,dogru_ad', [
        ('NASA-STD-5012',
         'Strength and Life Assessment Requirements for Liquid-Fueled'),
        ('NASA SP-8124', 'Liquid Rocket Engine Self-Cooled Combustion Chambers'),
        ('NASA SP-125', 'Design of Liquid Propellant Rocket Engines'),
        ('NASA SP-8089', 'Liquid Rocket Engine Injectors'),
        ('NASA SP-8110', 'Liquid Rocket Engine Turbines'),
        ('NASA SP-8007', 'Buckling of Thin-Walled Circular Cylinders'),
        ('ISO 898-1', 'Mechanical properties of fasteners'),
        ('AIAA S-080A', 'Metallic Pressure Vessels'),
        ('NFPA 1125', 'Manufacture of Model Rocket'),
        ('NACA Report 1135', 'Equations, Tables, and Charts for Compressible'),
    ])
    def test_dogrulanmis_baslik_defterde(self, defter, numara, dogru_ad):
        assert numara in defter
        assert dogru_ad in defter

    def test_dogrulanmayanlar_acikca_isaretli(self, defter):
        """Doğrulanmamış atıf 'doğru' gibi durmamalı."""
        assert 'DOĞRULANMADI' in defter

    def test_5012_nin_kodda_kullanilmadigi_yaziyor(self, defter):
        """Atıf tamamen yanlıştı; defter bunu saklamamalı."""
        assert 'Kodda kullanımı:** **YOK.**' in defter


# ---------------------------------------------------------------------------
# C1 — PDF teknik eki
# ---------------------------------------------------------------------------
class TestPdfTeknikEki:

    @staticmethod
    def _appendix_text(analysis_results):
        from hrma.export.pdf_generator import PDFReportGenerator
        story = PDFReportGenerator()._create_technical_appendix(
            {'motor_type': 'liquid'}, analysis_results)
        return '\n'.join(getattr(item, 'text', '') for item in story)

    def test_bos_kosuda_hicbir_yontem_iddiasi_yok(self):
        text = self._appendix_text({})
        assert 'No analysis sections were supplied' in text
        for kelime in ('NASA-standard', 'Bartz', 'isentropic',
                       'Analysis Assumptions'):
            assert kelime not in text, kelime

    def test_dolu_kosuda_gercek_kaynak_basiliyor(self):
        text = self._appendix_text({
            'performance': {'thrust': 5000.0, 'specific_impulse': 240.0},
            'thermal': {'wall_temperature': 800.0},
        })
        assert 'NACA Report 1135' in text          # performans kaynağı
        assert 'Bartz' in text                     # termal kaynak
        assert 'Analysis Assumptions' in text
        # Koşmayan bölümün varsayımı basılmamalı
        assert 'Thin-wall assumption' not in text

    def test_standart_uygunlugu_iddia_edilmiyor(self):
        text = self._appendix_text({
            'performance': {'thrust': 5000.0},
            'structural': {'safety_factor': 2.1},
            'safety': {'risk_assessment': {'risk_level': 'LOW'}},
        })
        assert 'not a statement of compliance' in text
        assert 'NASA-standard methodolog' not in text

    def test_sabit_standart_listesi_kaynaktan_kalkti(self):
        """Kaldırılan üç satır kodda kalmamalı.

        Kusuru anlatan düzeltme yorumu bu satırları alıntılıyor; alıntı
        muafiyet işaretiyle ayrıldığı için sayılmaz.
        """
        source = _read_without_exempt('hrma/export/pdf_generator.py')
        # IDDIA-LINT-MUAF-BASLANGIC (kaldırılan kusurun birebir alıntısı)
        assert 'NASA-STD-5012: Pressure Vessels' not in source
        assert 'NASA SP-8124: Thermal Design Criteria' not in source
        assert 'NASA SP-125: Liquid-Propellant Rocket Engine Performance' \
            not in source
        # IDDIA-LINT-MUAF-BITIS


# ---------------------------------------------------------------------------
# C2 / C3 — standart atıfları düzeltilen dosyalar
# ---------------------------------------------------------------------------
DUZELTILEN_DOSYALAR = (
    'hrma/templates/formulas.html',
    'hrma/static/js/i18n_formulas.js',
    'hrma/static/js/panels/performance_panel.js',
    'hrma/export/pdf_generator.py',
)


class TestStandartAtiflari:

    @pytest.mark.parametrize('rel_path', DUZELTILEN_DOSYALAR)
    def test_yanlis_baslik_geri_gelmedi(self, rel_path):
        hits = iddia_lint.scan_file(os.path.join(REPO_ROOT, rel_path))
        wrong = [f for f in hits
                 if f.rule_id in {r.rule_id
                                  for r in iddia_lint.WRONG_STANDARD_TITLES}]
        assert not wrong, [(f.line_no, f.matched) for f in wrong]

    def test_mach_alan_bagintisi_gercek_kaynagi_gosteriyor(self):
        """Alan-Mach bağıntısı standart gaz dinamiğidir, mukavemet
        standardı değil (nozzle_flow_1d.py:12-26 kaynak listesi)."""
        for rel in ('hrma/templates/formulas.html',
                    'hrma/static/js/i18n_formulas.js'):
            text = _read(rel)
            assert 'NACA Report 1135' in text or 'NACA Raporu 1135' in text, rel

    def test_5012_yalniz_dogru_konusuyla_aniliyor(self):
        """Belge adı geçebilir — ama yalnız 'burada kaynak değildi'
        açıklamasıyla; başlık da doğru yazılmalı."""
        for rel in ('hrma/templates/formulas.html',
                    'hrma/static/js/i18n_formulas.js',
                    'hrma/static/js/panels/performance_panel.js'):
            text = _read_flat(rel)
            if 'NASA-STD-5012' not in text:
                continue
            assert 'Strength and Life Assessment' in text, rel

    def test_sp8124_dogru_baslikla_aniliyor(self):
        for rel in ('hrma/templates/formulas.html',
                    'hrma/static/js/i18n_formulas.js',
                    'hrma/static/js/panels/performance_panel.js',
                    'hrma/export/pdf_generator.py'):
            text = _read_flat(rel)
            if 'SP-8124' not in text:
                continue
            assert 'Self-Cooled Combustion Chambers' in text, rel


# ---------------------------------------------------------------------------
# C4 — NASA gerçek zamanlı doğrulayıcı
# ---------------------------------------------------------------------------
class TestDogrulayiciHukumVermiyor:

    @pytest.fixture(scope='class')
    def sonuc(self):
        from hrma.data.nasa_realtime_validator import NASARealtimeValidator
        # F-1 boğaz çapı 914.4 mm; itki/Pc verilmezse ölçekleme yapılmaz.
        return NASARealtimeValidator().validate_motor_calculation(
            'F-1', 900.0)

    @pytest.mark.parametrize('yasak', [
        'NASA-grade',
        'Good accuracy for engineering purposes',
        'Acceptable for preliminary design',
        'EXCELLENT',
    ])
    def test_yasak_hukum_yok(self, sonuc, yasak):
        assert yasak not in str(sonuc), sonuc

    def test_sapma_yuzdesi_ve_kaynak_veriliyor(self, sonuc):
        metin = sonuc['recommendation']
        assert f"{sonuc['error_percent']:.2f}%" in metin
        assert sonuc['nasa_source'] in metin

    def test_karsilastirmanin_ne_olmadigi_yaziyor(self, sonuc):
        assert 'not a validation' in sonuc['recommendation']
        assert 'not a validation campaign' in sonuc['comparison_is_not']
        assert 'single published throat diameter' in sonuc['comparison_basis']

    def test_durum_etiketi_sapma_bandi(self, sonuc):
        assert sonuc['status'].startswith('DEVIATION')

    def test_tuketicinin_bekledigi_anahtarlar_duruyor(self, sonuc):
        """liquid_rocket_engine.py:2601-2604 bu alanları basıyor."""
        for key in ('color', 'status', 'calculated_mm', 'nasa_reference_mm',
                    'error_percent', 'recommendation'):
            assert key in sonuc, key

    def test_olcekleme_yapildiysa_beyan_ediliyor(self):
        from hrma.data.nasa_realtime_validator import NASARealtimeValidator
        # F-1 deniz seviyesi itkisi 6.77 MN; yarısını isteyince ölçeklenir.
        sonuc = NASARealtimeValidator().validate_motor_calculation(
            'F-1', 640.0, thrust_N=3.385e6, chamber_pressure_bar=70)
        assert 'scal' in sonuc['comparison_basis']
        assert 'sqrt(F/Pc)' in sonuc['recommendation']


# ---------------------------------------------------------------------------
# C5 — formül referans sayfası §14
# ---------------------------------------------------------------------------
class TestFormulSayfasiIddiasi:

    def test_html_basligi_ve_girisi_iddiasiz(self):
        text = _read('hrma/templates/formulas.html')
        assert 'not a statement of compliance with any standard' in text
        assert '14. NASA Standards Based Advanced Analysis' not in text

    @pytest.mark.parametrize('anahtar,beklenen', [
        ('fx.s14.h', 'Reference Relations Behind the Advanced Analysis'),
        ('fx.s14.h', 'İleri Analiz Figürlerinin Arkasındaki Bağıntılar'),
    ])
    def test_iki_dilde_de_yeni_baslik_var(self, anahtar, beklenen):
        text = _read('hrma/static/js/i18n_formulas.js')
        assert anahtar in text
        assert beklenen in text

    def test_turkce_metinde_turkce_karakterler_dogru(self):
        text = _read('hrma/static/js/i18n_formulas.js')
        assert 'İleri Analiz Figürlerinin Arkasındaki Bağıntılar' in text
        assert 'herhangi bir standarda uygunluk beyanı değildir' in text

    def test_koda_uymayan_sekil_fonksiyonlari_beyan_ediliyor(self):
        """visualization.py:2538-2545 ve :2904-2919 ölçümü: 14.1'in iki
        şekil fonksiyonu ve 14.3'ün eksenel/zamansal çarpanları
        2026-07-19'da koddan kaldırıldı; sayfa bunu söylemeli."""
        for rel in ('hrma/templates/formulas.html',
                    'hrma/static/js/i18n_formulas.js'):
            text = _read(rel)
            assert 'illustrative' in text or 'örnekleyici' in text, rel
