# -*- coding: utf-8 -*-
"""ÖH Dalga-19 · kulvar ALTYAPI · aşama a1 — bekçiler.

Kapsanan defter kalemleri
-------------------------
OH-B3-04   (ŞART, kanıt hijyeni) D17 ölçüm betiği adımın KENDİ gövdesini
           çıkarıyor mu — heredoc'suz `run:` satırı yabancı bir heredoc'a
           kaymamalı
P10B3-10   `g_0` / `R_universal` literalleri `hrma/` içinde bağımsız
           TANIMLANMIYOR (tek kaynak `hrma.constants`)
P10B4-14   `tools/cfd_referans_dondur.py` KİRLİ (ya da ölçülemeyen) çalışma
           ağacından dondurmayı REDDEDİYOR — beyan değil kapı
P13B1-03   Euler bit-özdeşlik sözleşmesi CI'da kuruluyor mu (iş akışı yarısı)
P10B3-23   NSIS betiği gerçekten derleniyor mu (etiket/sözdizim kilidi)

Her bekçi, onarımı geçici olarak GERİ ALDIĞINDA kırmızı verecek biçimde
yazıldı; ters-mutasyon kanıtı `docs/scofield/raw/OH/D19/altyapi/a1/
mutasyon.json` dosyasındadır.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import re
import shutil
import subprocess
import sys

import pytest
from tests.support.kanit import kanit_gerekli

DEPO = pathlib.Path(__file__).resolve().parents[1]
ISAKISI = DEPO / '.github' / 'workflows'
NSI = DEPO / 'packaging' / 'hrma.nsi'
D17_OLCUM = DEPO / 'docs/scofield/raw/OH/D17/altyapi/a1/olcum.py'

if str(DEPO) not in sys.path:                        # pragma: no cover
    sys.path.insert(0, str(DEPO))


# ---------------------------------------------------------------------------
# OH-B3-04 (ŞART) — kanıt betiği adımın KENDİ gövdesini çıkarıyor mu
# ---------------------------------------------------------------------------

def _d17_olcum_modulu():
    spec = importlib.util.spec_from_file_location('d17_olcum_altyapi',
                                                  kanit_gerekli(D17_OLCUM))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ÖH D36 kanit-atlama: eski ``skipif(not D17_OLCUM.exists())`` kaldırıldı —
# ithal anında değerlenen bir kapı docs'suz ağaçta modülün TAMAMINI atlardı,
# geliştirme ağacında ise kanıt silinse SESSİZCE atlardı. İki test de kanıtı
# ``_d17_olcum_modulu()`` üzerinden kapıdan (kanit_gerekli) geçerek okur.
class TestD17OlcumAdimGovdesi:
    """Fable-D17 ŞARTI: ölçüm YANLIŞ gövdeyi koşuyordu.

    `_yml_adim_betigi` yalnız ``<<'PY'`` heredoc'u arıyordu; OH-B3-04 onarımı
    adımı heredoc'suz düz bir kabuk satırına çevirince arama adımın sınırını
    aşıp dosyadaki BİR SONRAKİ heredoc'u (kapı 6/8 aynası) yakaladı ve
    ``SyntaxError('&')`` ile çıkış 1 verdi. sonra.json'daki "1 (KIRMIZI)"
    sayıları kapıdan DEĞİL bu hatadan geliyordu.
    """

    def test_heredocsuz_adim_govdesi_KENDI_adimindan_gelir(self):
        m = _d17_olcum_modulu()
        rel = (ISAKISI / 'release.yml').read_text(encoding='utf-8')
        adlar = re.findall(r'- name: (Atlama[^\n]*)', rel)
        assert adlar, 'release.yml`de Atlama adımı yok (adres göçtü)'
        govde = m._yml_adim_betigi(rel, adlar[0])
        assert govde.strip(), 'adım gövdesi boş çıktı'
        assert 'atlama_kapisi.py' in govde, (
            'çıkarılan gövde adımın KENDİSİ değil — betik adımın sınırını '
            f'aşıp başka bir bloğu yakaladı:\n{govde[:400]}')
        # Yabancı heredoc'a kayma imzası: 6/8 aynasının içeriği
        assert 'requests' not in govde and 'urlopen' not in govde, (
            f'gövdeye canlı duman testi bloğu karışmış:\n{govde[:400]}')

    def test_govde_kabukta_kosuluyor_ve_kapi_hukum_veriyor(self, tmp_path):
        """Gövde `python -c` ile değil KABUKTA koşulmalı; kapı hüküm vermeli."""
        m = _d17_olcum_modulu()
        rel = (ISAKISI / 'release.yml').read_text(encoding='utf-8')
        adlar = re.findall(r'- name: (Atlama[^\n]*)', rel)
        govde = m._yml_adim_betigi(rel, adlar[0])
        kod_asim, cikti_asim = m._adim_kos(govde, 300, 0)
        kod_tam, cikti_tam = m._adim_kos(govde, 76, 0, toplam=9497)
        assert 'SyntaxError' not in cikti_asim, (
            f'ölçüm hâlâ yabancı bir gövdeyi koşuyor:\n{cikti_asim[-400:]}')
        assert kod_asim == 1, (
            f'300 atlamada kapı YEŞİL (çıkış {kod_asim}):\n{cikti_asim[-400:]}')
        assert kod_tam == 0, (
            f'tam bütçede kapı KIRMIZI (çıkış {kod_tam}) — yanlış-kırmızı:'
            f'\n{cikti_tam[-400:]}')


# ---------------------------------------------------------------------------
# P10B3-10 — g_0 / R_universal tek kaynak
# ---------------------------------------------------------------------------

#: `hrma/` içinde çıplak literal olarak KALMASI kabul edilen siteler ve
#: gerekçeleri. Liste BÜYÜMEZ (ÖK-22): yeni bir bağımsız tanım kırmızıdır.
#: Kalanlar bu dalganın sahası DIŞINDA (kardeş kulvar dosyaları) ya da
#: DEĞERİ farklı (gerçek ayrışma, ayrı defter kalemi).
#:
#: ÖH D24 / P10B3-10 (fix aşaması) — LİSTE KÜÇÜLDÜ (4 site -> 1).
#: D19'da kalan dört sitenin üçü "kardeş kulvar dosyası / çakışma yasağı"
#: gerekçesiyle bekliyordu; o kilit fix aşamasında kalktığı için üçü de
#: artık merkezden okuyor:
#:   * external_data_fetcher (4×) -> R_UNIVERSAL. SAYI DEĞİŞTİ, BEYANLI:
#:     8 314,5 -> 8 314,462618; ``gas_constant`` bağıl -4,4960e-6.
#:   * hybrid_rocket_engine (3×)  -> R_UNIVERSAL. Sayı AYNI (8 314,462618).
#:   * app.py (1×)                -> G_0. Sayı AYNI (9,80665).
#: Ayrıca chemical_database 3× ``8.314`` -> ``R_MOLAR`` (bu sayı aşağıdaki
#: RU_DEGERLERI kümesinde olmadığı için burada hiç sayılmıyordu; bekçisi
#: tests/test_d24_fix_asamasi.py içindedir).
KALAN_CIPLAK_LITERALLER = {
    # 9.8 — YERÇEKİMİ DEĞİL: Inconel 625'in ısı iletkenliği k = 9,8 W/m/K
    # (Special Metals 625 veri sayfası; materials_db :637
    # ``thermal_conductivity`` ve :650 ``k_curve[294]``). D22'nin
    # "materials_db 9,8" g_0 iddiası ÖLÇÜLEREK ÇÜRÜTÜLDÜ; bu iki satır
    # merkeze BAĞLANMAMALIDIR (bağlanırsa malzeme verisi bozulur).
    'hrma/data/materials_db.py': 2,
}

G0_DEGERLERI = {9.80665, 9.81, 9.8}
RU_DEGERLERI = {8314.462618, 8314.46, 8314.5, 8314.0, 8314.4621, 8314.472}


def _literal_taramasi():
    """(bagimsiz_atamalar, ciplak_kullanimlar) — AST tabanlı."""
    atamalar, kullanimlar = [], []
    for yol in sorted((DEPO / 'hrma').rglob('*.py')):
        if yol.name == 'constants.py':
            continue
        try:
            agac = ast.parse(yol.read_text(encoding='utf-8'))
        except SyntaxError:                          # pragma: no cover
            continue
        rel = str(yol.relative_to(DEPO))
        atama_satirlari = set()
        for dugum in ast.walk(agac):
            if isinstance(dugum, (ast.Assign, ast.AnnAssign)):
                d = dugum.value
                if (isinstance(d, ast.Constant)
                        and isinstance(d.value, float)
                        and (d.value in G0_DEGERLERI or d.value in RU_DEGERLERI)):
                    atamalar.append(f'{rel}:{dugum.lineno} = {d.value}')
                    atama_satirlari.add(d.lineno)
        for dugum in ast.walk(agac):
            if (isinstance(dugum, ast.Constant)
                    and isinstance(dugum.value, float)
                    and dugum.lineno not in atama_satirlari
                    and (dugum.value in G0_DEGERLERI
                         or dugum.value in RU_DEGERLERI)):
                kullanimlar.append(rel)
    return atamalar, kullanimlar


class TestFizikselSabitTekKaynak:

    def test_bagimsiz_g0_Ru_TANIMI_kalmadi(self):
        """Ölçüldü (once_p10b3_10.json): 2 bağımsız modül düzeyi tanım vardı.

        `six_dof_trajectory.G0 = 9.80665` ve
        `acoustic_modes.R_UNIVERSAL_J_KMOL_K = 8314.462618` merkezî tanımdan
        KOPUKTU: `hrma.constants` güncellenirse bu iki sayı sessizce ayrışır.
        """
        atamalar, _ = _literal_taramasi()
        assert not atamalar, (
            'hrma/ içinde `g_0` / `R_universal` BAĞIMSIZ olarak tanımlanıyor '
            f'(hrma.constants`tan ithal edilmeli): {atamalar}')

    def test_ciplak_literal_envanteri_BUYUMEZ(self):
        """Kalan çıplak kullanımlar adıyla sayılır; yeni bir tanesi kırmızı."""
        _, kullanimlar = _literal_taramasi()
        sayim = {}
        for rel in kullanimlar:
            sayim[rel] = sayim.get(rel, 0) + 1
        fazla = {k: v for k, v in sayim.items()
                 if v > KALAN_CIPLAK_LITERALLER.get(k, 0)}
        assert not fazla, (
            f'yeni çıplak `g_0`/`R_universal` literali: {fazla} '
            f'(beklenen envanter: {KALAN_CIPLAK_LITERALLER})')
        olu = {k: v for k, v in KALAN_CIPLAK_LITERALLER.items()
               if sayim.get(k, 0) < v}
        assert not olu, (
            f'envanter ölü satır taşıyor (bu siteler artık merkezden okuyor, '
            f'listeyi küçültün): {olu}')

    def test_merkezden_okuyan_siteler_AYNI_sayiyi_veriyor(self):
        """Bağlama değeri değiştirmemeli: bit düzeyinde aynı sayı."""
        from hrma.constants import G_0, R_UNIVERSAL
        from hrma.analysis.acoustic_modes import R_UNIVERSAL_J_KMOL_K
        from hrma.analysis.safety_analysis import SAFETY_MODEL
        from hrma.analysis.six_dof_trajectory import G0
        from hrma.validation.user_data_validation import _THRUST_UNIT_FACTORS
        assert G0 == G_0 == 9.80665
        assert R_UNIVERSAL_J_KMOL_K == R_UNIVERSAL == 8314.462618
        assert SAFETY_MODEL['gravity_m_s2'] == G_0
        assert _THRUST_UNIT_FACTORS['kgf'] == G_0


# ---------------------------------------------------------------------------
# P10B4-14 — CFD referans dondurucusu KİRLİ ağacı REDDEDİYOR mu
# ---------------------------------------------------------------------------

class TestCfdReferansKirlilikKapisi:
    """Kirliliği künyeye yazmak ÇÖZÜM DEĞİLDİR; kapı gerekir.

    Ölçüldü (once_p10b4_14.json): sevk edilen dört Euler referansının dördü
    de `git_calisma_agaci_kirli: true`; araç bunu yazıyor ama reddetmiyordu.
    Ayrıca git ölçülemediğinde `('', False)` dönüyordu — "ölçemedim" hâli
    TEMİZ sayılıyordu (fail-OPEN).
    """

    @staticmethod
    def _arac():
        from tools import cfd_referans_dondur as t
        return t

    def test_kirli_agacta_dondurma_DURUR(self, monkeypatch):
        t = self._arac()
        monkeypatch.setattr(t, '_git_durumu',
                            lambda: ('abc123', True, ['hrma/app.py'], True))
        with pytest.raises(SystemExit) as e:
            t.kirlilik_kapisi()
        assert 'KİRLİ' in str(e.value), str(e.value)

    def test_git_olculemezse_dondurma_DURUR(self, monkeypatch):
        """FAIL-CLOSED: ölçemediğimiz ağacı TEMİZ ilan etmeyiz."""
        t = self._arac()
        monkeypatch.setattr(t, '_git_durumu', lambda: ('', None, [], False))
        with pytest.raises(SystemExit) as e:
            t.kirlilik_kapisi()
        assert 'ÖLÇÜLEMEDİ' in str(e.value), str(e.value)

    def test_acik_izin_GEREKCESIZ_kabul_edilmez(self, monkeypatch):
        t = self._arac()
        monkeypatch.setattr(t, '_git_durumu',
                            lambda: ('abc123', True, ['x.py'], True))
        with pytest.raises(SystemExit) as e:
            t.kirlilik_kapisi(izin=True, gerekce='   ')
        assert '--gerekce boş' in str(e.value), str(e.value)

    def test_acik_izin_gerekceyi_KUNYEYE_yazar(self, monkeypatch):
        t = self._arac()
        monkeypatch.setattr(t, '_git_durumu',
                            lambda: ('abc123', True, ['x.py'], True))
        kunye = t.kirlilik_kapisi(izin=True, gerekce='V0 öncesi acil dondurma')
        assert kunye['git_kirli_izin_gerekcesi'] == 'V0 öncesi acil dondurma'
        assert kunye['git_calisma_agaci_kirli'] is True
        assert kunye['git_durumu_olculebildi'] is True
        assert kunye['git_kirli_dosyalar'] == ['x.py']

    def test_temiz_agacta_kunye_temiz(self, monkeypatch):
        t = self._arac()
        monkeypatch.setattr(t, '_git_durumu',
                            lambda: ('abc123', False, [], True))
        kunye = t.kirlilik_kapisi()
        assert kunye['git_calisma_agaci_kirli'] is False
        assert kunye['git_kirli_izin_gerekcesi'] == ''

    def test_cli_kapiyi_dondurmadan_ONCE_cagiriyor(self):
        """Kapı `main()` içinde, ilk `dondur` çağrısından ÖNCE olmalı."""
        kaynak = (DEPO / 'tools' / 'cfd_referans_dondur.py').read_text(
            encoding='utf-8')
        i_main = kaynak.find('def main(')
        govde = kaynak[i_main:]
        i_kapi = govde.find('kirlilik_kapisi(')
        i_dondur = min((x for x in (govde.find('dondur_pb_none(zorla='),
                                    govde.find('dondur(kunye, zorla='))
                        if x >= 0), default=-1)
        assert i_kapi >= 0, 'main() kirlilik kapısını çağırmıyor'
        assert 0 <= i_kapi < i_dondur, (
            'kirlilik kapısı dondurma çağrısından SONRA — kirli referans '
            'zaten yazılmış olur')


# ---------------------------------------------------------------------------
# P10B3-23 — NSIS betiği GERÇEKTEN derleniyor mu (etiket/sözdizim kilidi)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which('makensis') is None, reason='makensis yok')
def test_hrma_nsi_derleniyor(tmp_path):
    """Grep bekçileri etiket hatasını görmez; derleyici görür.

    ÖH D19'da kurulum bölümüne `Call HrmaDizinKullanilabilirMi` + `Abort`
    dallanması eklendi; etiket adı yanlış yazılırsa yalnız `makensis` söyler.
    """
    calisma = tmp_path / 'nsis'
    (calisma / 'win' / 'payload' / 'python').mkdir(parents=True)
    (calisma / 'win' / 'payload' / 'libs').mkdir(parents=True)
    (calisma / 'win' / 'payload' / 'app').mkdir(parents=True)
    for alt in ('python', 'libs', 'app'):
        (calisma / 'win' / 'payload' / alt / 'x.txt').write_text('x')
    shutil.copy2(NSI, calisma / 'hrma.nsi')
    shutil.copy2(DEPO / 'packaging' / 'hrma.ico', calisma / 'hrma.ico')
    r = subprocess.run(
        ['makensis', '-V2', '-DVERSION=0.0.0', f'-DOUTDIR={calisma}',
         'hrma.nsi'],
        cwd=str(calisma), capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (
        f'packaging/hrma.nsi derlenmiyor:\n{r.stdout[-1500:]}\n{r.stderr[-800:]}')


# ---------------------------------------------------------------------------
# P10B3-15 — macOS paketinin Anaconda kaynaklı paketleri PİNLİ mi
# ---------------------------------------------------------------------------

MAC_BETIK = DEPO / 'packaging' / 'build_mac_app.sh'
ANACONDA_PIN = DEPO / 'packaging' / 'anaconda_paket_pinleri.txt'


def _anaconda_bolgesi():
    metin = MAC_BETIK.read_text(encoding='utf-8')
    i = metin.find('ANACONDA_SITE="${ANACONDA_SITE:-')
    j = metin.find('echo "      pinli bağımlılıklar')
    assert i >= 0 and j > i, 'Anaconda bölgesi bulunamadı (adres göçtü)'
    return metin[i:j]


def _pinler():
    kayit = {}
    for satir in ANACONDA_PIN.read_text(encoding='utf-8').split('\n'):
        s = satir.strip()
        if not s or s.startswith('#'):
            continue
        parca = s.split()
        if len(parca) >= 2:
            kayit[parca[0]] = parca[1]
    return kayit


class TestAnacondaPaketPinleri:
    """`cp -R` ile kopyalanan denge termokimyası SÜRÜMÜ ölçülür.

    Ölçüldü (once_p10b3_15.json): Anaconda yolu 3 yerde sabitti, sürüm pini
    yoktu, iki kopya `|| true` ile SESSİZ geçiliyordu, doğrulama yalnız
    `[ -d ... ]` idi. Boş bir `cantera/` dizini de "yerinde" sayılıyordu.
    """

    def test_pin_dosyasi_uc_paketi_de_tasiyor(self):
        pin = _pinler()
        for pkg in ('rocketcea', 'cantera', 'ruamel.yaml'):
            assert pkg in pin, f'{pkg} için sürüm pini yok: {sorted(pin)}'
            assert re.fullmatch(r'\d+(\.\d+)+', pin[pkg]), (
                f'{pkg} pini sürüm gibi görünmüyor: {pin[pkg]!r}')

    def test_sessiz_kopya_KALMADI(self):
        bolge = MAC_BETIK.read_text(encoding='utf-8')
        kod = '\n'.join(x for x in bolge.split('\n')
                        if not x.lstrip().startswith('#'))
        sessiz = re.findall(r'cp -R[^\n]*\|\|\s*true', kod)
        assert not sessiz, (
            f'Anaconda kopyası hâlâ sessizce geçiliyor: {sessiz}')

    def test_anaconda_yolu_TEK_KAYNAK(self):
        kod = '\n'.join(x for x in MAC_BETIK.read_text(encoding='utf-8').split('\n')
                        if not x.lstrip().startswith('#'))
        sabit = re.findall(r'/opt/anaconda3[^\s"\']*', kod)
        assert len(sabit) <= 1, (
            f'Anaconda yolu {len(sabit)} yerde sabit yazılı: {sabit} — '
            'tek kaynak `ANACONDA_SITE` olmalı')
        assert re.search(r'^ANACONDA_SITE="\$\{ANACONDA_SITE:-', kod, re.M), (
            'ANACONDA_SITE tek kaynak değişkeni yok')

    @pytest.mark.skipif(shutil.which('bash') is None, reason='bash yok')
    def test_pin_uyusmazliginda_derleme_DURUR(self, tmp_path):
        """Ters yön: pin tutmayan bir sürüm pakete GİREMEZ."""
        bolge = _anaconda_bolgesi()
        sahte_site = tmp_path / 'site'
        (sahte_site / 'rocketcea-9.9.9.dist-info').mkdir(parents=True)
        sahte_pin = tmp_path / 'pin.txt'
        sahte_pin.write_text('rocketcea 1.2.1\n', encoding='utf-8')
        betik = (f'set -uo pipefail\nB="{DEPO}/packaging"\n'
                 f'RES="{tmp_path}"\n{bolge}\nanaconda_pin_dogrula rocketcea\n')
        r = subprocess.run(
            ['bash', '-c', betik], capture_output=True, text=True, timeout=180,
            env={**__import__('os').environ,
                 'ANACONDA_SITE': str(sahte_site),
                 'ANACONDA_PIN_DOSYASI': str(sahte_pin)})
        assert r.returncode != 0, (
            f'pin 1.2.1 iken 9.9.9 sürümü kabul edildi:\n{r.stdout}{r.stderr}')
        assert 'pin' in (r.stdout + r.stderr).lower()

    @pytest.mark.skipif(shutil.which('bash') is None, reason='bash yok')
    def test_bos_kopya_YERINDE_sayilmaz(self, tmp_path):
        bolge = _anaconda_bolgesi()
        sahte_site = tmp_path / 'site'
        (sahte_site / 'cantera-3.1.0.dist-info').mkdir(parents=True)
        (tmp_path / 'libs' / 'cantera').mkdir(parents=True)
        sahte_pin = tmp_path / 'pin.txt'
        sahte_pin.write_text('cantera 3.1.0\n', encoding='utf-8')
        betik = (f'set -uo pipefail\nB="{DEPO}/packaging"\n'
                 f'RES="{tmp_path}"\n{bolge}\nanaconda_kopya_dogrula cantera\n')
        r = subprocess.run(
            ['bash', '-c', betik], capture_output=True, text=True, timeout=180,
            env={**__import__('os').environ,
                 'ANACONDA_SITE': str(sahte_site),
                 'ANACONDA_PIN_DOSYASI': str(sahte_pin)})
        assert r.returncode != 0, (
            f'BOŞ cantera/ dizini "yerinde" sayıldı:\n{r.stdout}{r.stderr}')


# ---------------------------------------------------------------------------
# P13B1-03 — Euler bit-özdeşlik sözleşmesi CI'da kuruluyor mu (iş akışı yarısı)
# ---------------------------------------------------------------------------

class TestEulerBitOzdesligiCidaKuruluyor:
    """Referanslar darwin/arm64'te donmuş; CI ubuntu → hep tolerans dalı.

    Sözleşme platformdan bağımsız kurulur: aynı vaka İKİ AYRI SÜREÇTE
    çözülüp korunumlu durumlar bit düzeyinde karşılaştırılır.
    """

    def test_tests_yml_kapiyi_cagiriyor(self):
        metin = (ISAKISI / 'tests.yml').read_text(encoding='utf-8')
        kod = '\n'.join(x for x in metin.split('\n')
                        if not x.lstrip().startswith('#'))
        assert 'tools/cfd_ci_bit_ozdeslik.py' in kod, (
            'CI Euler bit-özdeşlik sözleşmesini kurmuyor — 1e-12 beyanı '
            'ubuntu`da bir kez bile sınanmıyor (P13B1-03)')
        i = kod.find('tools/cfd_ci_bit_ozdeslik.py')
        oncesi = kod[max(0, i - 700):i]
        assert 'if: always()' in oncesi, (
            'adım `if: always()` değil — test adımı düşünce kapı da susar')

    def test_arac_iki_ayri_surecte_FARKLI_tohumla_cozuyor(self, monkeypatch):
        """İki alt süreç AYNI karma tohumuyla koşarsa süreç ömrüne bağlı
        etkiler (sözlük sırası, ilk çağrıda kurulan önbellekler) ölçülemez.
        Davranış ölçülür: `subprocess.run` yakalanır, tohumlar kıyaslanır.
        """
        import numpy as np
        from tools import cfd_ci_bit_ozdeslik as t

        cagrilar = []

        def _sahte_run(argv, **kw):
            cagrilar.append(kw.get('env', {}).get('PYTHONHASHSEED'))
            hedef = argv[argv.index('--_hedef') + 1]
            np.save(hedef, np.zeros((2, 2, 4)))

            class R:
                returncode = 0
                stdout = ''
                stderr = ''
            return R()

        monkeypatch.setattr(t.subprocess, 'run', _sahte_run)
        hukum = t.kos(['izantropik_60x12'])
        assert len(cagrilar) == 2, (
            f'vaka başına iki AYRI süreç koşmadı: {cagrilar}')
        assert cagrilar[0] != cagrilar[1], (
            'iki alt süreç AYNI PYTHONHASHSEED ile koştu '
            f'({cagrilar}) — süreç ömrüne bağlı etkiler görülmez')
        assert hukum['vakalar']['izantropik_60x12']['bit_ayni'] is True
        kaynak = (DEPO / 'tools' / 'cfd_ci_bit_ozdeslik.py').read_text(
            encoding='utf-8')
        assert 'subprocess.run' in kaynak and '--_coz' in kaynak, (
            'ikinci çözüm ayrı süreçte koşmuyor')

    def test_fark_sifirdan_buyukse_kapi_KAPANIR(self):
        from tools import cfd_ci_bit_ozdeslik as t
        hukum = {'vakalar': {'x': {'bit_ayni': False, 'max_mutlak_fark': 1e-9}}}
        kotu = [k for k, v in hukum['vakalar'].items() if not v.get('bit_ayni')]
        assert kotu, 'hüküm süzgeci ayrışmayı görmüyor'
        assert t.BEYAN_EDILEN_BANT == 1e-12
        kaynak = (DEPO / 'tools' / 'cfd_ci_bit_ozdeslik.py').read_text(
            encoding='utf-8')
        assert "if kotu:" in kaynak and 'return 1' in kaynak, (
            'ayrışmada araç çıkış kodu 1 vermiyor')

    def test_sozlesme_bu_platformda_KURULUYOR(self):
        """Gerçek koşum (2 vaka x 2 süreç ~20 s) — beyan ölçülür."""
        from tools import cfd_ci_bit_ozdeslik as t
        hukum = t.kos(['izantropik_60x12'])
        v = hukum['vakalar']['izantropik_60x12']
        assert v['hukum'] == 'BIT-AYNI', v
        assert v['max_mutlak_fark'] == 0.0, v
