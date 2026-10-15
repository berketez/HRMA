"""Z5S / P10-Z5S-E — kampanyanın KENDİ ölçüm araçlarının bekçileri.

Neden bu dosya var
------------------
Defteri ölçen araçlar kapısız ve fail-open'dı: referans defteri yoksa "her
şey yeni" diyorlardı, aklama yolları uydurma sabiti temize çıkarıyordu, ayna
listeleri senkron değildi ve iddia dilini denetleyen bekçi totolojikti.
Defterin kendi ölçüsü bozukken defterin hükümleri de bozuktur; bu dosya o
ölçüyü kilitler.

Kapatılan kalemler (hepsi 27 Ağustos 2026'da depo üzerinde ölçüldü):

* **P10B4-01** — ``iddia_lint`` kampanyanın kanıtladığı künye-yalanı
  sınıflarının 15'ini kaçırıyordu ve pre-commit kancası KURULU DEĞİLDİ
  (``.git/hooks/`` içinde yalnız ``commit-msg`` vardı), yani araç hiçbir
  kapıyı korumuyordu.
* **P10B4-03** — ``guaranteed`` kuralının ``allow_if`` muafiyeti 24
  karakterlik bir pencerede olumsuzlama sözcüğü arıyordu; "There is no
  doubt: results are guaranteed" akl(an)ıyordu.
* **P10B4-08** — sınıflandırıcının aklama yolları kampanyanın kendi
  uydurma-sabit örneklerini "beyanlı/tanım/kopya" diye kapatıyordu.
* **P10B4-09** — aklayan ayna listesi (7 kök) denetleyen listeden (5 kök)
  genişti ve senkron tutan bekçi yoktu.
* **P10B4-10 / P10B4-12** — üç aracın varsayılan girdisi depo DIŞINDAYDI ve
  o dosya kaybolmuştu; ``sabit_tarayici`` bunu sessizce yutup "temiz"
  veriyordu.
* **P10B4-11** — ``kusur_teyit``in yaprak evreni eksikti; yanıtta duran
  yapraklar "YAPRAK_YOK (kaldırılmış olabilir)" hükmü alıyordu.
* **P10B4-18** — ``iddia_lint``in yasak-ifade bekçisi totolojikti.

Bekçiler DAVRANIŞ ve KÜNYE kilitler; kesin ondalık çapalanmaz.
"""

import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if os.path.join(REPO_ROOT, 'tools') not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, 'tools'))

import kampanya_defteri                                   # noqa: E402
import kusur_teyit                                        # noqa: E402
import sabit_siniflandirma as ss                          # noqa: E402
from tests.support import shake                           # noqa: E402
from tests.test_faz4_iddia_dili import (                  # noqa: E402
    BAGIMSIZ_NEGATIF,
    BAGIMSIZ_POZITIF,
)
from tools import iddia_lint                              # noqa: E402


def _oku(rel: str) -> str:
    with open(os.path.join(REPO_ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


# ===========================================================================
# P10B4-01 — kapı GERÇEKTEN koşuyor mu?
# ===========================================================================
class TestIddiaLintKapisi:
    """Kapı testin İÇİNDE: pre-commit kurulumuna bağlı değil.

    Ölçüm (27 Ağu 2026): ``.pre-commit-config.yaml`` iddia_lint kancasını
    tanımlıyordu ama ``.git/hooks/pre-commit`` YOKTU (dizinde yalnız
    ``commit-msg``). Yani kanca hiç koşmamıştı. ``pre-commit install``
    çalıştırılmadıkça config bir kapı DEĞİLDİR; bu yüzden kapı buraya,
    sürüm kapısının koştuğu test süitine taşındı.
    """

    def test_cli_kapisi_yesil(self):
        """``tools/iddia_lint.py --check`` ALT SÜREÇ olarak koşar."""
        p = subprocess.run(
            [sys.executable, 'tools/iddia_lint.py', '--check'],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
        assert p.returncode == 0, p.stdout + p.stderr

    def test_cli_kapisi_kayitsiz_isabette_KIRMIZI(self, tmp_path):
        """Kapının kırmızıya dönebildiği gösterilir (yeşil ≠ kör)."""
        hedef = tmp_path / 'ihlal.py'
        hedef.write_text("TITLE = 'NASA-grade accurate results'\n",
                         encoding='utf-8')
        p = subprocess.run(
            [sys.executable, 'tools/iddia_lint.py', '--check',
             '--root', str(tmp_path)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
        assert p.returncode == 1, p.stdout + p.stderr
        assert 'KAPI KIRMIZI' in p.stdout

    def test_pre_commit_kancasi_hala_tanimli(self):
        """Kanca kolaylık olarak kalsın; sessizce silinmesi fark edilmeli."""
        metin = _oku('.pre-commit-config.yaml')
        assert 'id: iddia-lint' in metin
        assert 'tools/iddia_lint.py' in metin

    def test_kancanin_kapi_OLMADIGI_yazili(self):
        """Config'in kendisi, kapı olmadığını söylemek zorunda.

        Yoksa bir sonraki okuyucu yine "lint pre-commit'te var" diye
        korunduğunu sanar — bu kalemin doğuş sebebi tam olarak buydu.
        """
        metin = _oku('.pre-commit-config.yaml')
        assert 'NOT A GATE' in metin.upper()
        assert 'test_z5s_kampanya_araclari' in metin


# ===========================================================================
# P10B4-01 (b) — künye yalanı kural sınıfı
# ===========================================================================
class TestKunyeYalaniKurallari:

    def test_kunye_sinifi_kural_kumesinde(self):
        assert iddia_lint.KUNYE_YALANI, 'künye yalanı kuralları yok'
        for kural in iddia_lint.KUNYE_YALANI:
            assert kural in iddia_lint.ALL_RULES, kural.rule_id

    def test_turkce_kural_var(self):
        """Ürünün Türkçe yüzü hiçbir kuralın kapsamında değildi (ölçüldü).

        Sekiz i18n sözlüğü ve şablonların Türkçe metinleri taranıyordu ama
        kuralların tamamı İngilizceydi. Bekçi ölçüt olarak DAVRANIŞA bakar:
        Türkçe bir iddia cümlesi yakalanmalı.
        """
        turkce = [p for p, _k in BAGIMSIZ_POZITIF
                  if any(h in p for h in 'çğıöşüÇĞİÖŞÜ')]
        assert len(turkce) >= 3, 'Türkçe pozitif örnek yetersiz'

    @pytest.mark.parametrize('rule_id', [
        'accuracy_band', 'experimental_validation', 'cea_validated',
        'sigma_coverage', 'cfd_verified', 'safe_verdict_tr',
        'safe_verdict_en', 'standard_compliant_tr', 'provenance_label',
        'builtin_table_claim',
    ])
    def test_kural_kimlikleri_duruyor(self, rule_id):
        """Kural kimlikleri kayıt defterinin ANAHTARIDIR; yeniden adlandırma
        bütün kayıtları sessizce bayatlatır."""
        assert rule_id in iddia_lint.RULES_BY_ID

    def test_kayit_defteri_yeni_kurallarin_isabetlerini_tasiyor(self):
        """Yeni kurallar ağaçta isabet üretti ve hepsi KAYDA girdi.

        Kayıt susturma değil envanterdir: her satır ya gerekçeli meşru
        kullanımdır ya AÇIK BORÇ'tur. Borçlar sıfırlanmışsa bu bekçi de
        anlamını yitirir, o yüzden borç VARLIĞI değil GÖRÜNÜRLÜĞÜ sınanır.
        """
        baseline = iddia_lint.load_baseline()
        kurallar = {k for _p, k, _h in baseline}
        assert 'cea_validated' in kurallar
        for (_p, _k, _h), gerekce in baseline.items():
            assert len(gerekce.strip()) >= 10


# ===========================================================================
# P10B4-03 — allow_if muafiyeti
# ===========================================================================
class TestAllowIfKapsami:

    KACAKLAR = [
        "DOC = 'There is no doubt: the result is guaranteed to 3 sigma.'",
        "NOTE = 'No risk is guaranteed to stay below the limit.'",
    ]
    MESRULAR = [
        '# the Joukowsky peak is NOT guaranteed to be the upper bound',
        '# accuracy is never guaranteed for an off-design point',
        '# there is no guarantee that the peak is bounded',
    ]

    @pytest.mark.parametrize('satir', KACAKLAR)
    def test_yakinlik_muafiyeti_artik_kacirmiyor(self, satir, tmp_path):
        hedef = tmp_path / 'ornek.py'
        hedef.write_text(satir + '\n', encoding='utf-8')
        assert iddia_lint.scan_file(str(hedef)), satir

    @pytest.mark.parametrize('satir', MESRULAR)
    def test_gercek_olumsuzlama_hala_muaf(self, satir, tmp_path):
        hedef = tmp_path / 'ornek.py'
        hedef.write_text(satir + '\n', encoding='utf-8')
        assert not iddia_lint.scan_file(str(hedef)), satir

    def test_aklanan_satirlar_RAPORLANIYOR(self, tmp_path):
        """Muafiyetin ne yuttuğu görünür olmalı — sessiz eleme yok."""
        hedef = tmp_path / 'ornek.py'
        hedef.write_text(
            '# the peak is NOT guaranteed to be the upper bound\n',
            encoding='utf-8')
        aklananlar = []
        bulgular = iddia_lint.scan_file(str(hedef), aklananlar=aklananlar)
        assert not bulgular
        assert len(aklananlar) == 1
        kayit = aklananlar[0]
        assert kayit.rule_id == 'guaranteed'
        assert 'guarantee' in kayit.matched.lower()
        assert kayit.muafiyet, 'muafiyetin yakaladığı metin kayıtlı değil'

    def test_cli_aklananlari_listeliyor(self):
        p = subprocess.run(
            [sys.executable, 'tools/iddia_lint.py', '--aklananlar'],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
        assert p.returncode == 0, p.stdout + p.stderr
        assert 'allow_if ile AKLANAN' in p.stdout


# ===========================================================================
# P10B4-10 / P10B4-12 — defter fail-closed ve depo İÇİNDE
# ===========================================================================
class TestDefterFailClosed:

    def test_varsayilan_defter_depo_icinde_ve_VAR(self):
        yol = kampanya_defteri.VARSAYILAN_DEFTER
        assert yol.startswith(REPO_ROOT), yol
        assert os.path.exists(yol), (
            f'kampanya defteri yok: {yol} — araçlar ölçemez')

    @pytest.mark.parametrize('arac', [
        'tools/sabit_tarayici.py',
        'tools/kusur_teyit.py',
        'tools/kusur_partileri.py',
    ])
    def test_arac_depo_disi_yol_TANIMLAMIYOR(self, arac):
        """Üç araç da aynı sabiti kendi dosyasında tanımlıyordu (üç kopya).

        Ölçüm: yol ``~/HRMA-kurtarma/takim-raporlari/sabit-bulgular.json``
        idi ve dizin YOKTU. Artık tek kaynak ``tools/kampanya_defteri.py``.
        """
        metin = _oku(arac)
        assert 'expanduser' not in metin, (
            f'{arac} hâlâ depo dışı bir varsayılan yol kuruyor')
        assert 'VARSAYILAN_DEFTER' in metin, (
            f'{arac} tek kaynaktan okumuyor')

    def test_defter_yoksa_YUKSELIR(self, tmp_path):
        yok = str(tmp_path / 'olmayan.json')
        with pytest.raises(kampanya_defteri.DefterYok):
            kampanya_defteri.defteri_yukle(yok)
        with pytest.raises(kampanya_defteri.DefterYok):
            kampanya_defteri.bilinen_yollar(yok)
        with pytest.raises(kampanya_defteri.DefterYok):
            kampanya_defteri.kusurlari_yukle(yok)

    @pytest.mark.parametrize('icerik', ['{}', '[]', '{"gruplar": []}',
                                        '{"gruplar": [{"ad": "x"}]}'])
    def test_bicim_taninmazsa_YUKSELIR(self, icerik, tmp_path):
        hedef = tmp_path / 'defter.json'
        hedef.write_text(icerik, encoding='utf-8')
        with pytest.raises(kampanya_defteri.DefterHatasi):
            kampanya_defteri.defteri_yukle(str(hedef))

    def test_sessiz_bos_kume_YOK(self, tmp_path):
        """Fail-open kusurunun tam biçimi: dosya yokken ``set(), set()``.

        Eski davranış bu iki boş kümeyi döndürüyor, ardından tarayıcı
        "bilinen kusur 0, bilinen meşru 0, YENİ 0" basıp çıkış kodu 0
        veriyordu — referans hiç okunmamışken "temiz" hükmü.
        """
        import sabit_tarayici
        with pytest.raises(kampanya_defteri.DefterHatasi):
            sabit_tarayici.bilinen_yollar(str(tmp_path / 'yok.json'))

    def test_defter_kapsam_sinirini_BEYAN_EDIYOR(self):
        """MEŞRU sınıfı kurtarılamadı; bu ölçüm değil kapsam sınırıdır."""
        _gruplar, kunye = kampanya_defteri.defteri_yukle()
        assert kunye, 'defter künyesiz — kapsamı okunamaz'
        beyan = kampanya_defteri.kapsam_beyani(kunye)
        assert beyan, 'kapsam beyanı boş'
        assert 'MEŞRU' in beyan

    def test_defter_138_kusuru_tasiyor(self):
        """Kampanyanın kapanış defteri yeniden ÖLÇÜLEBİLİR durumda."""
        kusurlar = kampanya_defteri.kusurlari_yukle()
        assert len(kusurlar) == 138, len(kusurlar)
        yaprak_yollu = [k for k in kusurlar
                        if (k.get('yol') or '').startswith('.')]
        assert len(yaprak_yollu) >= 100
        for k in kusurlar[:20]:
            assert k.get('_grup'), 'grup adı kaybolmuş'

    def test_tarayici_defter_yoksa_TEMIZ_DEMIYOR(self, tmp_path):
        """Uçtan uca: çıkış kodu 0 (temiz) DEĞİL."""
        p = subprocess.run(
            [sys.executable, 'tools/sabit_tarayici.py', '--sayfa', 'solid',
             '--rapor', str(tmp_path / 'yok.json'),
             '--cikti', str(tmp_path / 'cikti.json')],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
            env={**os.environ, 'PYTHONPATH': REPO_ROOT})
        assert p.returncode != 0, p.stdout
        assert 'ÖLÇEMEDİM' in (p.stdout + p.stderr)


# ===========================================================================
# P10B4-11 — kusur_teyit yaprak evreni
# ===========================================================================
class TestKusurTeyitYaprakEvreni:
    """Üçüncü küme sentetik ölçümle sınanır (HTTP koşumu gerekmez).

    Gerçek ölçüm (27 Ağu 2026) sayıları verdi: taban yanıtta katı 3.189,
    sıvı 3.406, hibrit 37.100 yaprak var; eski evren (``sabit ∪ oynayan``)
    bunların %22,0 / %19,5 / %5,9'unu içermiyordu. Defterdeki 130 yaprak
    yollu kusurun hükmü buna bağlı olarak 32 ``YAPRAK_YOK``tan 10'a indi;
    22 kalem artık ``YANKI`` diye ADIYLA raporlanıyor.
    """

    @staticmethod
    def _olcum():
        taban = {
            '.motor.sabit_sayi': 42.0,
            '.motor.canli_sayi': 7.0,
            '.chamber_pressure': 70.0,          # yalnız yankı olarak oynar
            '.motor.etiket': 'metin',           # sayısal değil
            '.inputs_not_used[0].submitted': 3000.0,   # beyan yankısı
            '.trajectory.motor_data.canli_sayi': 7.0,  # ayna kopyası
        }
        sabit = {'.motor.sabit_sayi'}
        oynayan = {'.motor.canli_sayi'}
        return {'liquid': {
            'sabit': sabit,
            'oynayan': oynayan,
            'yanki': set(taban) - sabit - oynayan,
            'taban_degerleri': taban,
            'tum_yapraklar': set(taban) | sabit | oynayan,
            'ozet': 'sentetik',
        }}

    def _hukum(self, yol):
        kusur = [{'yol': yol, '_grup': 'sıvı sayfası', '_sayfa': 'liquid',
                  'deger': None, 'guven': 'yuksek'}]
        return kusur_teyit.teyit_et(kusur, self._olcum())[0]

    def test_sabit_yaprak_hala_sabit(self):
        assert self._hukum('.motor.sabit_sayi')['sonuc'] == 'HALA_SABIT'

    def test_oynayan_yaprak_kapali(self):
        assert self._hukum('.motor.canli_sayi')['sonuc'] == 'KAPALI'

    def test_yankida_kalan_yaprak_YAPRAK_YOK_DEMEZ(self):
        """Kusurun kendisi: yanıtta 70,0 değeriyle duran yaprağa
        "yol yanıtta yok — kaldırılmış olabilir" deniyordu."""
        h = self._hukum('.chamber_pressure')
        assert h['sonuc'] == 'YANKI', h
        assert 'yanıtta VAR' in h['neden']

    def test_gercekten_yok_olan_yaprak_YAPRAK_YOK(self):
        h = self._hukum('.motor.hic_olmayan')
        assert h['sonuc'] == 'YAPRAK_YOK'

    @pytest.mark.parametrize('yol,ipucu', [
        ('.inputs_not_used[0].submitted', 'beyan yankısı'),
        ('.trajectory.motor_data.canli_sayi', 'ayna kopyası'),
        ('.motor.etiket', 'sayısal olmayan'),
    ])
    def test_yanki_gerekcesi_ADIYLA_yaziliyor(self, yol, ipucu):
        """Üçüncü küme "artık" değil, gerekçeli bir sınıf olmak zorunda."""
        h = self._hukum(yol)
        assert h['sonuc'] == 'YANKI', h
        assert ipucu in h['neden'], h['neden']

    def test_olc_ucuncu_kumeyi_donduruyor(self):
        """Sözleşme bekçisi: ``olc()`` çıktısında üç küme de bulunmalı."""
        kaynak = _oku('tools/kusur_teyit.py')
        assert "'yanki'" in kaynak
        assert 'baseline_leaves' in kaynak, (
            'yaprak evreni hâlâ sabit ∪ oynayan üstünden kuruluyor olabilir')
        assert 'YANKI' in kaynak


# ===========================================================================
# P10B4-08 — sınıflandırıcının aklama yolları
# ===========================================================================
class TestAklamaYollari:

    def test_available_soneki_kaldirildi(self):
        """``cea_isp_s_available = True`` sayının NEREDEN geldiğini söylemez.

        Ölçüldü: bu sonek üç sayfanın sabit kümelerinde (162/305/199) tek
        bir yaprağı bile kapatmıyordu, yani kaldırmanın maliyeti sıfır.
        """
        assert '_available' not in ss.BEYAN_SONEKLERI

    def test_bool_bayrak_artik_aklamiyor(self):
        yapraklar = {'.motor.cea_isp_s': 285.0,
                     '.motor.cea_isp_s_available': True}
        sinif, _g = ss.siniflandir('.motor.cea_isp_s', 285.0, yapraklar)
        assert sinif == 'SINIFLANDIRILMAMIS', sinif

    def test_fiziksel_oran_1_0_tanim_sayilmaz(self):
        """``expansion_ratio = 1.0`` "lüle yok" demektir, normalizasyon değil."""
        yapraklar = {'.motor.expansion_ratio': 1.0}
        sinif, _g = ss.siniflandir('.motor.expansion_ratio', 1.0, yapraklar)
        assert sinif != 'tanim', sinif

    def test_gercek_normalizasyon_hala_tanim(self):
        """Dokunulmayan yol bit-aynı davranmalı: deniz seviyesi referansı."""
        yol = '.altitude_performance[0].thrust_ratio'
        sinif, gerekce = ss.siniflandir(yol, 1.0, {yol: 1.0})
        assert sinif == 'tanim', (sinif, gerekce)

    def test_ayrisik_ayna_AKLANMAZ(self):
        """Kanonik canlı 5000,0 iken donmuş 4200,0 kopya "kopya" sayılıyordu."""
        yapraklar = {'.motor.thrust_n': 5000.0,
                     '.trajectory.motor_data.thrust_n': 4200.0}
        sonuc = ss.siniflandir_hepsi(['.trajectory.motor_data.thrust_n'],
                                     yapraklar)
        yol, sinif, gerekce = sonuc['kalemler'][0]
        assert sinif != 'kopya', (sinif, gerekce)
        assert 'AYNA AYRISIK' in gerekce
        assert any(a['dal'] == 'ayna(ayrisik)' for a in sonuc['aklananlar'])

    def test_bit_ayni_ayna_hala_kopya(self):
        yapraklar = {'.motor.thrust_n': 5000.0,
                     '.trajectory.motor_data.thrust_n': 5000.0}
        sonuc = ss.siniflandir_hepsi(['.trajectory.motor_data.thrust_n'],
                                     yapraklar)
        _yol, sinif, _g = sonuc['kalemler'][0]
        assert sinif == 'kopya'

    def test_tip_kaymasi_kopya_sayilmaz(self):
        """``True == 1`` ve ``1 == 1.0`` doğrudur ama bunlar kopya değil."""
        yapraklar = {'.motor.thrust_n': 5000, '': None,
                     '.trajectory.motor_data.thrust_n': 5000.0}
        sonuc = ss.siniflandir_hepsi(['.trajectory.motor_data.thrust_n'],
                                     yapraklar)
        _yol, sinif, _g = sonuc['kalemler'][0]
        assert sinif != 'kopya', 'int/float kayması kopya sayıldı'

    def test_zayif_aklama_AYRI_SINIF_ve_YAYIMLANIYOR(self):
        """Küçük blok muafiyeti: beyan metni yaprağın adını hiç anmıyor.

        Ölçüldü: bu dal üç sayfada 44 yaprağı (solid 27, liquid 13,
        hybrid 4) kapatıyordu ve ``beyanli`` sayımının içinde görünmezdi.
        """
        yapraklar = {
            '.blok.dimensional_accuracy_percent': 99.5,
            '.blok.strand_burner_tests': 5,
            '.blok.basis': 'Malzeme fiyatlari 2024 ortalama piyasa verisi.',
        }
        sonuc = ss.siniflandir_hepsi(['.blok.dimensional_accuracy_percent'],
                                     yapraklar)
        _yol, sinif, gerekce = sonuc['kalemler'][0]
        assert sinif == 'beyanli_zayif', (sinif, gerekce)
        assert 'ZAYIF' in gerekce
        yayimlanan = [a['yol'] for a in sonuc['aklananlar'] if a['aklandi']]
        assert '.blok.dimensional_accuracy_percent' in yayimlanan

    def test_jetonu_eslesen_beyan_GUCLU_kaliyor(self):
        """Adını anan beyan zayıf sınıfa düşmemeli (aşırı sıkma yok)."""
        yapraklar = {
            '.blok.dimensional_accuracy_percent': 99.5,
            '.blok.basis': 'dimensional accuracy percent imalat toleransidir',
        }
        sinif, _g = ss.siniflandir('.blok.dimensional_accuracy_percent',
                                   99.5, yapraklar)
        assert sinif == 'beyanli'

    def test_siniflandir_hepsi_aklananlar_ANAHTARINI_donduruyor(self):
        sonuc = ss.siniflandir_hepsi([], {})
        assert 'aklananlar' in sonuc
        assert 'sayim' in sonuc and 'kalemler' in sonuc


# ===========================================================================
# P10B4-09 — ayna listeleri senkron
# ===========================================================================
class TestAynaKokleriSenkron:

    @staticmethod
    def _shake_kokleri():
        return {(o + '.', k + '.') for o, k in shake.ECHO_CANONICAL_PREFIXES}

    def test_denetlenen_kokler_SHAKE_TEN_geliyor(self):
        assert set(ss.AYNA_KOKLERI_DENETLENEN) == self._shake_kokleri()

    def test_aklayan_liste_denetleyeni_KAPSIYOR(self):
        """Aklayan liste denetleyenden dar olamaz; geniş olan kısım
        gerekçesiyle ayrı listededir."""
        assert self._shake_kokleri() <= set(ss.AYNA_KOKLERI)

    def test_fazlaliklarin_HEPSI_gerekceli(self):
        for kok, gerekce in ss.AYNA_KOKLERI_DENETLENMEYEN.items():
            assert isinstance(gerekce, str) and len(gerekce) > 40, kok

    def test_hicbir_kok_iki_listede_degil(self):
        ortak = set(ss.AYNA_KOKLERI_DENETLENEN) & set(
            ss.AYNA_KOKLERI_DENETLENMEYEN)
        assert not ortak, ortak

    def test_ayna_kokleri_iki_listenin_TOPLAMI(self):
        assert set(ss.AYNA_KOKLERI) == (
            set(ss.AYNA_KOKLERI_DENETLENEN)
            | set(ss.AYNA_KOKLERI_DENETLENMEYEN))

    def test_denetlenmeyen_kok_de_BIT_AYNILIK_istiyor(self):
        """Denetlenmeyen kök shake bekçisine girmiyor; o yüzden aklama
        sınıflandırma anında ölçülür."""
        yapraklar = {'.nozzle_angles.x': 30.0,
                     '.motor.nozzle_angles.x': 15.0}
        sonuc = ss.siniflandir_hepsi(['.nozzle_angles.x'], yapraklar)
        _yol, sinif, gerekce = sonuc['kalemler'][0]
        assert sinif != 'kopya', (sinif, gerekce)

    def test_bit_ayni_olcutu_TEK_kaynakta(self):
        """Ölçüt ``shake``te tanımlıdır, araçta ikinci kez yazılmaz."""
        assert shake.bit_ayni(1.0, 1.0)
        assert not shake.bit_ayni(1, 1.0)
        assert 'shake.bit_ayni' in _oku('tools/sabit_siniflandirma.py')


# ===========================================================================
# P10B4-18 — korpus bağımsızlığı (mutasyon kanıtı test_faz4_iddia_dili'nde)
# ===========================================================================
class TestKorpusBagimsizligi:

    def test_korpus_bos_degil(self):
        assert len(BAGIMSIZ_POZITIF) >= 15
        assert len(BAGIMSIZ_NEGATIF) >= 5

    def test_her_ornegin_KAYNAGI_yazili(self):
        for satir, kaynak in BAGIMSIZ_POZITIF + BAGIMSIZ_NEGATIF:
            assert satir.strip(), 'boş örnek'
            assert len(kaynak.strip()) >= 10, (satir, kaynak)

    def test_pozitif_korpus_kural_metninden_kopya_degil(self):
        kural_metni = ' '.join(
            (r.pattern + ' ' + r.why + ' ' + (r.allow_if or ''))
            for r in iddia_lint.ALL_RULES).lower()
        for satir, _k in BAGIMSIZ_POZITIF:
            assert satir.strip().lower() not in kural_metni, satir

    def test_korpus_birden_cok_kurali_kapsiyor(self):
        """Tek bir kuralın etrafında dönen korpus da totolojiktir."""
        import tempfile
        kapsanan = set()
        with tempfile.TemporaryDirectory() as d:
            for i, (satir, _k) in enumerate(BAGIMSIZ_POZITIF):
                yol = os.path.join(d, f'k{i}.py')
                with open(yol, 'w', encoding='utf-8') as fh:
                    fh.write(satir + '\n')
                kapsanan |= {f.rule_id for f in iddia_lint.scan_file(yol)}
        assert len(kapsanan) >= 8, sorted(kapsanan)


# ===========================================================================
# Araçların uçtan uca koşabildiği (defter geri geldi)
# ===========================================================================
class TestAraclarKosuyor:

    def test_kusur_partileri_kosuyor(self, tmp_path):
        cikti = tmp_path / 'partiler.json'
        p = subprocess.run(
            [sys.executable, 'tools/kusur_partileri.py',
             '--cikti', str(cikti)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=900)
        assert p.returncode == 0, p.stdout + p.stderr
        with open(cikti, encoding='utf-8') as fh:
            sonuc = json.load(fh)
        assert sonuc['toplam_kusur'] == 138
        assert sonuc['parti_sayisi'] >= 2
        assert sonuc.get('defter_kapsam_beyani'), (
            'parti çıktısı defterin kapsam sınırını taşımıyor')
