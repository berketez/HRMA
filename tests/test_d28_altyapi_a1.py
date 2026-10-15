# -*- coding: utf-8 -*-
"""ÖH Dalga-28 · altyapi · aşama-1 bekçileri.

Kalemler
--------
* **OH-D27-04** — ``tools/iddia_lint.py`` release_gate.sh / CI kapısına bağlı
  değildi (ölçüldü: ``.github/`` ağacında 0, ``packaging/`` ağacında 0 isabet;
  tek bağı testler ve pre-commit kancasıydı). Araç aynı ölçümde KIRMIZIYDI
  (``--check`` çıkış kodu 1, kayıtsız isabet 1).
* **OH-D27-07** — ``hrma/data/changelog.json`` 2.6.27 notu yedi sözleşme
  değişikliğini anmıyordu (yedi kodun 7'si üründe canlı, notta 0).
* **Havuz** — yayın iş akışının taslak gövdesi ve iş özeti kapı adımlarını
  ELLE numaralıyordu ve bir satırı ölçümle YANLIŞTI ("8/8 paket içerik
  denetimi | release_gate.sh'ta böyle bir adım yok").

Kanıt: ``docs/scofield/raw/OH/D28/altyapi/a1/{once,sonra,mutasyon}.json``.
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re
import subprocess
import sys

import pytest

DEPO = pathlib.Path(__file__).resolve().parents[1]
KAPI_BETIGI = DEPO / 'packaging' / 'release_gate.sh'
TESTS_YML = DEPO / '.github' / 'workflows' / 'tests.yml'
RELEASE_YML = DEPO / '.github' / 'workflows' / 'release.yml'
IDDIA_LINT = DEPO / 'tools' / 'iddia_lint.py'
BASELINE = DEPO / 'tools' / 'iddia_lint_baseline.txt'
OZET_ARACI = DEPO / 'tools' / 'yayin_kapi_ozeti.py'
CHANGELOG = DEPO / 'hrma' / 'data' / 'changelog.json'

#: Aracı ÇALIŞTIRAN satır deseni — adı anmak (yorumda geçmek) yetmez.
CALISTIRMA = re.compile(r'(python3?|\$PY|\$\{PY\})\s+\S*tools/iddia_lint\.py')


def _kapi_metni():
    return KAPI_BETIGI.read_text(encoding='utf-8')


def _kapi_bolumu(baslik_parcasi):
    """Kapı adımını BAŞLIĞINDAN kes; bulunamazsa açıkça patla."""
    metin = _kapi_metni()
    i = metin.find(baslik_parcasi)
    assert i >= 0, f'kapıda {baslik_parcasi!r} adımı YOK'
    j = metin.rfind('baslik "', 0, i)
    assert j >= 0, f'{baslik_parcasi!r} başlık satırı yok'
    sonrasi = metin.find('\nbaslik "', j + 1)
    return metin[j:sonrasi if sonrasi > 0 else len(metin)]


def _kod(govde):
    """Yorumları at — kapı betiği gerekçesini gövdesinde anlatıyor."""
    return '\n'.join(s for s in govde.splitlines()
                     if not s.lstrip().startswith('#'))


# ===========================================================================
# OH-D27-04 — araç yayın kapısına ve CI'a BAĞLI
# ===========================================================================
class TestOHD2704IddiaLintKapiyaBagli:
    """Ölçülen kusur: araç 28 kuralla duruyordu ama hiçbir yayın kapısında
    koşmuyordu. pre-commit YEREL bir kolaylıktır: kurmayan katkıcıda
    sessizce yoktur ve yayın yolunda hiç çalışmaz."""

    def test_yayin_kapisinda_araci_CALISTIRAN_bir_adim_var(self):
        govde = _kod(_kapi_bolumu('İddia dili (kazanılmamış hüküm) kapısı'))
        assert CALISTIRMA.search(govde), (
            'kapı adımı aracı çalıştırmıyor (adı anmak yetmez):\n'
            + govde[:600])
        assert '--check' in govde, 'kapı kipi (--check) kullanılmıyor'

    def test_kapi_adimi_FAIL_CLOSED(self):
        """Kayıtsız isabet varsa kapı KAPANIR; 'atlandi' demez."""
        govde = _kod(_kapi_bolumu('İddia dili (kazanılmamış hüküm) kapısı'))
        assert 'basarisiz "iddia dili kapısı KALDI' in govde, govde[:600]
        assert 'atlandi' not in govde, (
            'iddia dili adımı ATLANABİLİR hâle gelmiş — "denetleyemedim" bir '
            'geçiş gerekçesi değildir:\n' + govde[:600])

    def test_kapi_adimi_hicbir_atlama_bayragi_gormez(self):
        govde = _kod(_kapi_bolumu('İddia dili (kazanılmamış hüküm) kapısı'))
        for bayrak in ('TAKIMI_ATLA', 'HIZLI', 'KAPIYI_ATLA'):
            assert bayrak not in govde, f'{bayrak} bayrağı adımı atlatıyor'

    def test_kapi_ACIK_BORC_sayisini_da_basiyor(self):
        """Borçlar taşınabilir ama görünmez kalamaz (ÖK-22 değil, dürüstlük)."""
        govde = _kod(_kapi_bolumu('İddia dili (kazanılmamış hüküm) kapısı'))
        assert '--debt' in govde, (
            'kapı açık borç sayısını basmıyor — kayıt defteri susturma aracına '
            'dönüşür:\n' + govde[:600])

    @pytest.mark.parametrize('yol', [TESTS_YML, RELEASE_YML],
                             ids=['tests.yml', 'release.yml'])
    def test_CI_is_akisi_araci_kosturuyor(self, yol):
        metin = yol.read_text(encoding='utf-8')
        calistiran = [s.strip() for s in metin.splitlines()
                      if CALISTIRMA.search(s) and not s.lstrip().startswith('#')]
        assert calistiran, (
            f'{yol.name} aracı çalıştıran bir adım taşımıyor — ölçüm (once.json) '
            'bu iş akışında 0 isabet göstermişti')
        assert any('--check' in s for s in calistiran), calistiran

    def test_arac_kapi_kipinde_BUGUN_YESIL(self):
        """Kapıya bağlanan araç gerçekten geçiyor mu (ölçüm, iddia değil).

        Ölçülen 'önce': çıkış kodu 1, kayıtsız isabet 1. Kapıya bağlamadan
        önce o isabet okunup kayıt defterine gerekçesiyle yazıldı.
        """
        r = subprocess.run([sys.executable, str(IDDIA_LINT), '--check'],
                           cwd=str(DEPO), capture_output=True, text=True,
                           timeout=600)
        assert r.returncode == 0, (
            'iddia_lint kapı kipinde KIRMIZI — yayın kapısı kapalı:\n'
            + r.stdout[-2000:])
        assert 'kayıtsız 0' in r.stdout, r.stdout[-500:]

    def test_pre_commit_config_UC_DOGRUDAN_kapiyi_adiyla_aniyor(self):
        """Config'in anlatısı bayatlamasın.

        Dosya "THIS FILE IS NOT A GATE ON ITS OWN" diyor ve kapının nerede
        olduğunu gösteriyordu: yalnız test süiti. OH-D27-04 o bağın DOLAYLI
        olduğunu ölçtü; bağ artık üç yerde DOĞRUDAN. Anlatı üçünü de adıyla
        anmalı, yoksa bir sonraki okuyucu yine yanlış yerde arar.
        """
        metin = (DEPO / '.pre-commit-config.yaml').read_text(encoding='utf-8')
        # Dosyanın HERHANGİ bir yerinde geçmesi yetmez: `release_gate.sh`
        # zaten en üstteki gerekçe paragrafında anılıyordu, yani gevşek bir
        # iddia bayat bir dosyada da yeşil kalırdı. Ölçü, kalemin AÇTIĞI
        # bloğun içidir.
        i = metin.find('ÖH D28 / altyapi (defter OH-D27-04')
        assert i > 0, 'OH-D27-04 anlatı bloğu config dosyasında yok'
        blok = metin[i:i + 1200]
        for ad in ('packaging/release_gate.sh',
                   '.github/workflows/tests.yml',
                   '.github/workflows/release.yml'):
            assert ad in blok, f'{ad} kalemin anlatı bloğunda anılmıyor'

    def test_kayit_defteri_D27_birlesmesinin_isabetini_GEREKCELI_tasiyor(self):
        """Susturma değil envanter — ve envanter İKİ YÖNLÜ okunur.

        ÖH D28 fix-28a (9 Eylül 2026) — KUSURU KORUYAN BEKÇİ ÇEVRİLDİ.
        Bu iddia "defterde şu satır BULUNMALI" diyordu ve öznesi olan
        isabetin ağaçta yaşayıp yaşamadığını hiç sormuyordu. Ölçüldü:
        ``9563f338`` (ÖH D27 fix-27a, A2) taahhüt dilini KAYNAKTA söktü ve
        "kayıt defterine YAZILMADI" dedi; D28 altyapi a1 ise kendi dalında
        (taban ``7cd08bcc``, sözcük orada hâlâ vardı) aynı isabeti DEFTERE
        yazdı. İkisi ana ağaçta buluşunca defter satırı öksüz kaldı:
        tarama 89 isabet, defter 90 satır, ölü 1 — ve bu iddia ölü satırı
        ayakta TUTUYORDU (``test_d15_bekci_cevirisi_a1`` ölü-kayıt
        bekçisiyle birbirini yiyorlardı; ikisi aynı anda yeşil olamıyordu).

        Ölçüt artık taramaya bağlı: isabet CANLIYSA defter onu gerekçeli
        taşımalı, ÖLÜYSE defter onu taşımamalı. İki yön de fail-closed.
        """
        from tools import iddia_lint
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                tarama = iddia_lint.scan()
        hedef = ('hrma/engines/hybrid_rocket_engine.py', 'guaranteed')
        canli = {(f.path, f.rule_id) for f in tarama}
        metin = BASELINE.read_text(encoding='utf-8')
        satir = [s for s in metin.splitlines()
                 if s.startswith('hrma/engines/hybrid_rocket_engine.py')
                 and '| guaranteed |' in s]

        if hedef in canli:
            assert len(satir) == 1, satir
            assert 'MEŞRU:' in satir[0], satir[0][:200]
            assert 'AÇIK BORÇ' not in satir[0], (
                'isabet açık borç olarak yazılmış; oysa determinist bir '
                'kod özelliği anlatılıyor')
            # Gerekçe dayanağını ADIYLA anmalı — "meşru" kanıt değildir.
            assert 'oxidizer_depleted' in satir[0], satir[0][:200]
            return

        # İsabet YOK: defter de taşımamalı, yoksa envanter yalancı olur.
        assert not satir, (
            'iddia_lint taramasında `guaranteed` isabeti YOK ama kayıt '
            'defteri onu hâlâ taşıyor — ölü kayıt: %r' % (satir[0][:200],))
        # Kapanış KAYNAKTA olmalı: hüküm kaybolmadan kip değişmiş olmalı.
        kaynak = (DEPO / 'hrma' / 'engines'
                  / 'hybrid_rocket_engine.py').read_text(encoding='utf-8')
        assert 'oxidizer_depleted' in kaynak, (
            'taahhüt dili söküldü ama dayanağı da kayboldu: künye artık '
            'hangi kod yolunun koştuğunu (end_event "oxidizer_depleted") '
            'söylemiyor')
        assert 'tank_model_envelope_basis' in kaynak, (
            'künye alanının kendisi kaybolmuş; kapanış "anlam korundu, '
            'yalnız kip değişti" olmaktan çıkmış')


# ===========================================================================
# Havuz — yayın beyanı TEK KAYNAKTAN türetilir
# ===========================================================================
class TestYayinKapiBeyaniTekKaynak:
    """Ölçülen kusur: taslak gövdesi ve iş özeti kapı adımlarını elle
    numaralıyordu (1/8..7/8) ve kapı 9 adıma çıkınca beyan bayatladı; bir
    satır ölçümle YANLIŞTI."""

    def _tablo(self):
        r = subprocess.run([sys.executable, str(OZET_ARACI), '--tablo'],
                           cwd=str(DEPO), capture_output=True, text=True,
                           timeout=180)
        assert r.returncode == 0, r.stderr
        return r.stdout

    def test_tablo_kapinin_HER_adimini_iceriyor(self):
        tablo = self._tablo()
        basliklar = re.findall(r'^baslik "(\d+)/(\d+)\s+([^"]*)"',
                               _kapi_metni(), flags=re.M)
        assert basliklar
        for numara, payda, baslik in basliklar:
            assert f'| {numara}/{payda} {baslik.strip()} |' in tablo, (
                f'{numara}/{payda} {baslik} tabloda yok', tablo)

    def test_iddia_dili_adimi_KOSTU_diye_beyan_ediliyor(self):
        """Türkçe küçültme tuzağı: 'İ'.lower() 'i'+U+0307 üretir.

        Eşleme bu yüzden sessizce düşüyor ve adım 'beyan edilmedi'
        görünüyordu — fail-closed tarafa düşen ama yine de YANLIŞ bir beyan.
        """
        tablo = self._tablo()
        satir = [s for s in tablo.splitlines() if 'İddia dili' in s]
        assert len(satir) == 1, tablo
        assert 'iddia_lint.py --check' in satir[0], satir[0]
        assert 'beyan edilmedi' not in satir[0], satir[0]

    def test_tanimsiz_adim_KOSTU_sayilmaz(self, tmp_path):
        """FAIL-CLOSED: durum tablosunda karşılığı olmayan adım uydurulmaz."""
        sahte = tmp_path / 'sahte_gate.sh'
        sahte.write_text(
            'baslik "1/2  Surum tutarliligi"\n'
            'baslik "2/2  Hic tanimlanmamis yepyeni adim"\n',
            encoding='utf-8')
        r = subprocess.run(
            [sys.executable, str(OZET_ARACI), '--tablo', '--betik', str(sahte)],
            cwd=str(DEPO), capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, r.stderr
        satir = [s for s in r.stdout.splitlines() if 'yepyeni adim' in s]
        assert len(satir) == 1, r.stdout
        assert 'beyan edilmedi' in satir[0], satir[0]

    def test_adimsiz_betikte_arac_KIRILIR(self, tmp_path):
        bos = tmp_path / 'bos.sh'
        bos.write_text('#!/bin/bash\necho merhaba\n', encoding='utf-8')
        r = subprocess.run(
            [sys.executable, str(OZET_ARACI), '--tablo', '--betik', str(bos)],
            cwd=str(DEPO), capture_output=True, text=True, timeout=180)
        assert r.returncode != 0, r.stdout
        assert 'KAPI ADIMI OKUNAMADI' in (r.stdout + r.stderr)

    def test_tutarsiz_payda_KIRMIZI(self, tmp_path):
        """Adım eklenip payda güncellenmezse beyan uydurulmaz, iş kırılır."""
        sahte = tmp_path / 'tutarsiz.sh'
        sahte.write_text(
            'baslik "1/2  Surum tutarliligi"\n'
            'baslik "2/2  Git durumu"\n'
            'baslik "3/2  Sonradan eklenen"\n', encoding='utf-8')
        r = subprocess.run(
            [sys.executable, str(OZET_ARACI), '--tablo', '--betik', str(sahte)],
            cwd=str(DEPO), capture_output=True, text=True, timeout=180)
        assert r.returncode == 1, r.stdout
        assert 'TUTARSIZ' in (r.stdout + r.stderr)

    def test_release_yml_elle_yazilmis_adim_tablosu_TASIMIYOR(self):
        metin = RELEASE_YML.read_text(encoding='utf-8')
        kod = _kod(metin)
        assert 'böyle bir adım yok' not in kod, (
            'ölçümle YANLIŞ beyan hâlâ basılıyor')
        # Çalışan kodda elle yazılmış `N/M` adım satırı kalmamalı.
        elle = [s for s in kod.splitlines()
                if re.search(r'echo "\|\s*\d+/\d+\s', s)]
        assert not elle, elle
        assert 'yayin_kapi_ozeti.py --tablo' in kod
        assert 'yayin_kapi_ozeti.py --gerekce' in kod

    def test_release_yml_beyan_uretilemezse_taslak_GOVDESI_yazilmaz(self):
        kod = _kod(RELEASE_YML.read_text(encoding='utf-8'))
        i = kod.find('yayin_kapi_ozeti.py --gerekce')
        assert i > 0
        kuyruk = kod[i:i + 400]
        assert 'exit 1' in kuyruk, (
            'beyan üretilemeyince iş devam ediyor — gövde uydurulur:\n'
            + kuyruk)


# ===========================================================================
# OH-D27-07 — 2.6.27 sürüm notu sözleşme değişikliklerini anıyor
# ===========================================================================
def _surum_2627():
    with CHANGELOG.open(encoding='utf-8') as fh:
        cl = json.load(fh)
    # karar §28-19/§28-46: yayımlanmamış 2.6.27 kaydı 3.0.0 adıyla çıkar.
    return next(v for v in cl['versions'] if v['version'] == '3.0.0')


#: (kod, ürün dosyası) — kod ÜRÜNDE canlı olmalı ve İKİ DİLDE anılmalı.
SOZLESME_KODLARI = [
    ('sweep_interval_not_supplied', 'hrma/app.py'),
    ('unread_field', 'hrma/app.py'),
    ('tank_pressure_not_read_in_turbopump_cycle', 'hrma/app.py'),
    ('unknown_fuel', 'hrma/app.py'),
    ('incomplete_flow_input', 'hrma/app.py'),
    ('accepted_range', 'hrma/app.py'),
    ('defaults_applied', 'hrma/app.py'),
]


class TestOHD2707SurumNotuSozlesmeleri:
    """Ölçülen kusur: yedi kodun 7'si üründe canlıydı, sürüm notunda 0'ı
    geçiyordu — dış istemci kırıcı değişikliği sürüm notundan öğrenemezdi."""

    @pytest.mark.parametrize('kod,dosya', SOZLESME_KODLARI,
                             ids=[k for k, _ in SOZLESME_KODLARI])
    def test_kod_hem_URUNDE_hem_IKI_DILDE_notta(self, kod, dosya):
        urun = (DEPO / dosya).read_text(encoding='utf-8')
        assert kod in urun, f'{kod} üründe yok — not bayat olabilir'
        v = _surum_2627()
        assert kod in v['notes_en'], f'{kod} İngilizce notta yok'
        assert kod in v['notes_tr'], f'{kod} Türkçe notta yok'

    @pytest.mark.parametrize('kod', [k for k, _ in SOZLESME_KODLARI[:5]])
    def test_ret_kodu_URUNDE_422_ile_donuyor(self, kod):
        """Not '422' diyor; ürün gerçekten 422 mı (beyan ⟷ kod)."""
        metin = (DEPO / 'hrma' / 'app.py').read_text(encoding='utf-8')
        i = metin.find(f"'error': '{kod}'")
        assert i > 0, f'{kod} bir ret gövdesinde geçmiyor'
        kuyruk = metin[i:i + 4000]
        assert re.search(r'\}\), 422', kuyruk), (
            f'{kod} 422 döndürmüyor ama sürüm notu öyle diyor:\n'
            + kuyruk[:400])

    def test_accepted_range_KIRICI_degisiklik_olarak_yaziliyor(self):
        v = _surum_2627()
        assert 'breaking change' in v['notes_en'], v['notes_en'][-1500:]
        assert 'kırıcı değişiklik' in v['notes_tr'], v['notes_tr'][-1500:]
        for dil in ('notes_en', 'notes_tr'):
            assert 'allowed_range' in v[dil], (
                f'{dil}: eski ad anılmıyor — istemci neyi değiştireceğini '
                'bilemez')

    def test_eski_kanon_URUNDE_gercekten_yok(self):
        """Not "tek kanonik ad" diyor; ürün onu doğruluyor mu."""
        metin = (DEPO / 'hrma' / 'app.py').read_text(encoding='utf-8')
        canli = [s.strip() for s in metin.splitlines()
                 if 'allowed_range' in s and not s.lstrip().startswith('#')]
        assert canli == [], canli

    def test_6dof_defaults_applied_kanali_URUNDE_var(self):
        metin = (DEPO / 'hrma' / 'app.py').read_text(encoding='utf-8')
        assert "_govde_6dof['defaults_applied']" in metin, (
            'sürüm notu 6-DOF beyan kanalını anlatıyor ama üründe yok')
        # Notun "sözleşme bit-aynı bırakıldı" cümlesinin dayanağı.
        assert 'input_defaults_substituted' in metin

    def test_notlar_UYDURMA_YASAGINI_soyluyor(self):
        v = _surum_2627()
        assert 'no value is invented' in v['notes_en']
        assert 'UYDURULMAZ' in v['notes_tr']


# ===========================================================================
# OH-D27-11 (altyapi payı) — bağımsız çevirici tanımları
# ===========================================================================
#: Kalem "altyapi 4 tanım" diyor. ÖLÇÜLDÜ (once.json) — dördü de aynı sınıfta
#: DEĞİL:
#:   * ``importers/motor_file.py:_to_float``   — taban uygulama
#:   * ``importers/ork_import.py:_to_float``   — İKİNCİ uygulamaydı (33/33
#:     vakada aynı sonuç; ``'auto'`` dalı ölü kod). Artık tabanı gösteriyor.
#:   * ``importers/ork_import.py:_child_float`` — ince sarmalayıcı, kendi
#:     çevirisi yok (``_to_float``a devrediyor) — bağımsız tanım değil.
#:   * ``utils/projects.py:_is_finite_number`` — ÇEVİRİCİ DEĞİL: JSON'a
#:     güvenle yazılabilirlik yüklemi (float olmayanlara True döner).
#: Merkez ``hrma/utils/input_guard.py``e bağlama bu dalgada ENGELLİ: kardeş
#: dal ölçümü ihracat kulvarının o dosyaya dokunduğunu gösterdi.
CEVIRICI_KORPUSU = [
    None, '', '   ', '0', '0,5', '0.5', '1,5', '3.2e3', 'auto', 'AUTO',
    'Auto 5', 'auto3', '3auto', 'nan', 'NaN', 'inf', '-inf', 'Infinity',
    '1,2,3', '1.2.3', 'abc', '  7,25  ', 7, 7.5, True, False,
    '1e400', '-0', ',5', '5,', '1,000.5',
]


class TestOHD2711AltyapiCevirileri:

    def test_ork_import_ceviricisi_TEK_TANIMI_gosteriyor(self):
        from hrma.importers import motor_file, ork_import
        assert ork_import._to_float is motor_file._to_float, (
            'ork_import yeniden kendi çeviri uygulamasını taşıyor — iki kopya '
            'ayrışabilir (defter OH-D27-11)')

    def test_child_float_kendi_cevirisini_YAPMIYOR(self):
        """Sarmalayıcı çeviriyi DEVREDİYOR mu, kopyalıyor mu (AST ölçüsü).

        Metin araması burada yanıltır: fonksiyonun KENDİ adı ``_child_float``
        zaten ``float(`` alt dizgesini taşır. Ölçü çağrı ağacından alınır.
        """
        import ast as _ast
        import inspect
        import textwrap
        from hrma.importers import ork_import
        agac = _ast.parse(textwrap.dedent(
            inspect.getsource(ork_import._child_float)))
        cagrilar = {d.func.id for d in _ast.walk(agac)
                    if isinstance(d, _ast.Call) and isinstance(d.func, _ast.Name)}
        assert '_to_float' in cagrilar, cagrilar
        assert 'float' not in cagrilar, (
            'sarmalayıcı kendi float() çevirisini yapıyor', cagrilar)

    @pytest.mark.parametrize('deger', CEVIRICI_KORPUSU,
                             ids=[repr(x) for x in CEVIRICI_KORPUSU])
    def test_iki_iceri_aktarici_AYNI_degeri_donduruyor(self, deger):
        """Devretmenin davranış koruduğunun kanıtı (fark 0/33 ölçüldü)."""
        from hrma.importers import motor_file, ork_import
        assert ork_import._to_float(deger) == motor_file._to_float(deger)

    def test_auto_metni_hala_None(self):
        """Silinen dalın vaadi devretmeden SONRA da tutuyor mu."""
        from hrma.importers import ork_import
        for metin in ('auto', 'AUTO', 'Auto 5', 'auto3'):
            assert ork_import._to_float(metin) is None, metin

    def test_projects_yuklemi_CEVIRICI_DEGIL(self):
        """Envanterin 4. adı bir çevirici değil; merkeze bağlanacak şey değil.

        ``_is_finite_number`` yalnız "JSON'a güvenle yazılabilir mi" sorusunu
        yanıtlar: float olmayan her değere True döner. input_guard.num()
        semantiğine çevrilmesi davranışı DEĞİŞTİRİRDİ.
        """
        from hrma.utils.projects import _is_finite_number
        assert _is_finite_number('metin') is True
        assert _is_finite_number(3) is True
        assert _is_finite_number(float('nan')) is False
        assert _is_finite_number(float('inf')) is False
        assert _is_finite_number(1.5) is True
