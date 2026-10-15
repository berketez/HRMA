"""ÖH Dalga-18 / altyapi a1 — paketleme kapıları, geliştirici araçları ve
tarayıcı iskelesinin hüküm katmanı.

Bu dosyadaki her sınıf bir defter kalemine bağlıdır ve her iddia TERS
MUTASYONLA kanıtlanmıştır (onarım geçici olarak geri alınınca ilgili test
KIRMIZI verir; kanıt: ``docs/scofield/raw/OH/D18/altyapi/a1/mutasyon.json``).

Ortak ilke: bu kulvarın kalemlerinin çoğu KAPI kalemidir. Bir kapının
kusuru "yanlış sayı basmak" değil, kazanılmamış bir hükmü GEÇİRMEKTİR —
o yüzden testler hep "sağlıksız girdi kapıyı DÜŞÜRÜYOR mu" diye sorar,
ve yanında "sağlıklı girdi hâlâ GEÇİYOR mu" ikizini taşır (yanlış-kapanma
da bir kusurdur).
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tools'))


# ---------------------------------------------------------------------------
# P17B1-20 (Fable-D15 ŞART) — rozet⟷yük çaprazı BİLGİ rozetlerinin sayısını
# da soruyor mu?
#
# ŞART METNİ: "denetimler._capraz_beklentileri bilgi rozetlerinin SAYISINI
# da yükle çaprazlasın — MESH DISTORTION n/N sayacı, CONVERGED 'in k rounds
# to x%' tur sayısı/toleransı, tane ACCEPTANCE METRIC son değişim yüzdesi
# (yük özeti anahtarları payload'dan)."
#
# ÖLÇÜM (olcum_p17b1_20.py, aynı süpürme):
#   ÖNCE  25/56 yakalanıyor (%44,6) — sil 13/22, renk 5/15, sayı 7/19
#   SONRA 55/56 yakalanıyor (%98,2) — sil 22/22, renk 15/15, sayı 18/19
# Tek kaçan: `SECTION: BATES · 1/8 slice` sayı mutasyonu; bozulan sayı
# ŞABLON literalidir ('1/{n} slice'), yükte karşılığı yoktur.
# ---------------------------------------------------------------------------
class TestP17B1_20BilgiRozetiSayilari:
    @staticmethod
    def _denetle(ad, olcum, panel):
        from tools.browser_harness import denetimler
        sonuc = [denetimler.fea_rozet_denetimi(
            ad, olcum, panel.beklenen_imzalar,
            getattr(panel, 'yasak_imzalar', ()))]
        capraz = denetimler.fea_yuk_caprazi_denetimi(ad, olcum)
        if capraz is not None:
            sonuc.append(capraz)
        return all(d.gecti for d in sonuc)

    @staticmethod
    def _panel(ad):
        from tools.browser_harness import sayfalar
        from tests.test_browser_harness_fea import (
            yapisal_olcum, termal_olcum, tane_olcum)
        return {
            'yapisal': (yapisal_olcum, sayfalar.YAPISAL_FEA),
            'termal': (termal_olcum, sayfalar.TERMAL_FEA),
            'tane': (tane_olcum, sayfalar.TANE_FEA),
        }[ad]

    def test_taban_uc_panelde_de_yesil(self):
        """Yanlış-kapanma ikizi: sağlıklı ölçüm hâlâ geçmeli."""
        for ad in ('yapisal', 'termal', 'tane'):
            kurucu, panel = self._panel(ad)
            assert self._denetle(ad, kurucu(), panel), f'{ad} tabanı kırmızı'

    #: (panel, rozet metninde aranan parça, ekrana yazılacak BOZUK metin)
    #: — her biri BİLGİ rozetidir; hüküm rozetleri D16 sınıfında kilitli.
    BOZMALAR = [
        ('yapisal', 'MESH DISTORTION',
         'MESH DISTORTION (scaled Jacobian < 0.5): 512/1024 flagged'),
        ('yapisal', 'MESH DISTORTION',
         'MESH DISTORTION (scaled Jacobian < 0.9): 0/1024 flagged'),
        ('yapisal', 'ELONGATED ELEMENTS',
         'ELONGATED ELEMENTS (aspect ratio > 4): 3/1024 — expected'),
        ('yapisal', 'CONVERGED in', 'CONVERGED in 9 rounds to 0.55%'),
        ('yapisal', 'CONVERGED in', 'CONVERGED in 3 rounds to 7.55%'),
        ('yapisal', 'MESH 1024', 'MESH 999 elements / 1105 nodes'),
        ('yapisal', 'MESH 1024', 'MESH 1024 elements / 7 nodes'),
        ('termal', 'MESH 64', 'MESH 64 elements / 4242 nodes'),
        ('termal', 'ENERGY RESIDUAL', 'ENERGY RESIDUAL 9.1e-15 (relative)'),
        ('termal', 'ENERGY RESIDUAL', 'ENERGY RESIDUAL 4.6e-03 (relative)'),
        ('tane', 'ACCEPTANCE METRIC',
         'ACCEPTANCE METRIC (bore strain) CONVERGED — last change '
         '0.5% (tolerance 1%)'),
        ('tane', 'ACCEPTANCE METRIC',
         'ACCEPTANCE METRIC (bore strain) CONVERGED — last change '
         '0.0007914% (tolerance 25%)'),
        ('tane', 'PEAK vM', 'PEAK vM still refining 88.4% — not the '
                            'acceptance basis'),
        ('tane', 'MESH 6144', 'MESH 6144 elements / 1 nodes'),
    ]

    @pytest.mark.parametrize('panel_adi,parca,bozuk', BOZMALAR)
    def test_bilgi_rozeti_sayisini_bozmak_yakalanir(self, panel_adi, parca,
                                                    bozuk):
        kurucu, panel = self._panel(panel_adi)
        olcum = copy.deepcopy(kurucu())
        idx = [i for i, r in enumerate(olcum['rozetler'])
               if parca in r.get('metin', '')]
        assert idx, f'{panel_adi}: {parca!r} rozeti fikstürde yok'
        olcum['rozetler'][idx[0]]['metin'] = bozuk
        assert not self._denetle(panel_adi, olcum, panel), (
            f'{panel_adi}/{parca}: BİLGİ rozetinin sayısı yükle '
            f'çaprazlanmıyor — ekranda {bozuk!r} yazıyor ve tur geçti')

    @pytest.mark.parametrize('panel_adi,parca', [
        ('yapisal', 'MESH DISTORTION'),
        ('yapisal', 'ELONGATED ELEMENTS'),
        ('yapisal', 'MESH 1024'),
        ('yapisal', 'ENGINE:'),
        ('termal', 'ENERGY RESIDUAL'),
        ('tane', 'ACCEPTANCE METRIC'),
        ('tane', 'SECTION:'),
    ])
    def test_bilgi_rozetini_silmek_yakalanir(self, panel_adi, parca):
        kurucu, panel = self._panel(panel_adi)
        olcum = copy.deepcopy(kurucu())
        idx = [i for i, r in enumerate(olcum['rozetler'])
               if parca in r.get('metin', '')]
        assert idx, f'{panel_adi}: {parca!r} rozeti fikstürde yok'
        del olcum['rozetler'][idx[0]]
        olcum['rozet_sayisi'] = len(olcum['rozetler'])
        assert not self._denetle(panel_adi, olcum, panel), (
            f'{panel_adi}/{parca}: yükte VAR olan rozetin ekrandan '
            'silinmesi turdan geçti')

    def test_sayac_esik_sayisiyla_karistirilmaz(self):
        """Tolerans tuzağı: `< 0.5` eşiği "0 bayraklı" sayacını karşılamaz.

        Sayaçlar ondalık toleransıyla (0 basamak → ±0,5) sorulsaydı,
        metindeki 0.5 eşiği beklentiyi karşılar ve 512/1024 mutasyonu
        KAÇARDI. Bu yüzden sayaçlar 'tam' kipiyle sorulur.
        """
        from tools.browser_harness import denetimler, esikler
        hedef, tolerans = denetimler._sayi_hedefi(0, 'tam')
        assert hedef == 0
        assert tolerans == esikler.FEA_CAPRAZ_TAM_SAYI_TOLERANSI
        assert abs(0.5 - hedef) > tolerans, (
            'sayaç toleransı eşik sayısını yutuyor')

    def test_anlamli_basamak_kipi_urunun_fmtSig_kuralini_aynalar(self):
        """`fmtSig(v, 4)` → 4 anlamlı basamak (fea_panel.js:458)."""
        from tools.browser_harness import denetimler
        hedef, tolerans = denetimler._sayi_hedefi(0.00079141234, 'sig4')
        assert hedef == pytest.approx(0.0007914, rel=1e-12)
        assert abs(0.0007914 - hedef) <= tolerans

    def test_yuk_ozeti_suzgeci_capraza_gereken_bloklari_tasiyor(self):
        """Tur JS'i `flags`/`mesh_info`/`energy` bloklarını KAYDEDİYOR mu?

        Çapraz bu üç bloktan besleniyor; tur onları atarsa beklenti hiç
        doğmaz ve kusur sessizce geri gelir.
        """
        from tools.browser_harness import tur
        for anahtar in ('flags', 'mesh_info', 'energy', 'engine_layout',
                        'grain_type', 'symmetry_fraction', 'convergence'):
            assert "'%s'" % anahtar in tur.JS_FEA_PANEL_DURUMU, (
                f'tur yuk_ozeti süzgeci {anahtar!r} bloğunu taşımıyor')


# ---------------------------------------------------------------------------
# P10B3-17 — restore_build_inputs.sh derleme girdisi YOKKEN "hazır" diyordu
# ---------------------------------------------------------------------------
BETIK_RESTORE = ROOT / 'packaging' / 'restore_build_inputs.sh'


def _restore_kos(win_var: bool, mac_var: bool, bos: bool = False):
    """Sahte depoda betiği koşturur; gerçek ~/.hrma-build-cache'e dokunmaz."""
    tmp = tempfile.mkdtemp(prefix='d18-restore-')
    try:
        depo = pathlib.Path(tmp) / 'depo'
        (depo / 'packaging').mkdir(parents=True)
        shutil.copy2(BETIK_RESTORE, depo / 'packaging' /
                     'restore_build_inputs.sh')
        for var, rel in ((win_var, 'packaging/win/payload'),
                         (mac_var, 'packaging/mac/libs')):
            if not var:
                continue
            d = depo / rel
            d.mkdir(parents=True)
            if not bos:
                (d / 'icerik.txt').write_text('x', encoding='utf-8')
        ev = pathlib.Path(tmp) / 'ev'
        ev.mkdir()
        return subprocess.run(
            ['bash', str(depo / 'packaging' / 'restore_build_inputs.sh')],
            capture_output=True, text=True, timeout=120,
            env=dict(os.environ, HOME=str(ev)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class TestP10B3_17DerlemeGirdisiKapisi:
    def test_saglikli_agac_gecer(self):
        """Yanlış-kapanma ikizi: iki girdi de doluysa kapı GEÇMELİ."""
        p = _restore_kos(True, True)
        assert p.returncode == 0, p.stdout + p.stderr
        assert 'Paketleme yapılabilir' in p.stdout

    @pytest.mark.parametrize('win,mac,bos,neden', [
        (False, False, False, 'ikisi de yok'),
        (True, False, False, 'mac/libs yok'),
        (False, True, False, 'win/payload yok'),
        (True, True, True, 'ikisi de BOŞ dizin'),
    ])
    def test_eksik_girdi_kapiyi_dusurur(self, win, mac, bos, neden):
        p = _restore_kos(win, mac, bos)
        assert p.returncode != 0, (
            'girdi eksikken (%s) kapı GEÇTİ: %s' % (neden, p.stdout))
        assert 'PAKETLEME YAPMA' in p.stdout
        assert 'Paketleme yapılabilir' not in p.stdout

    def test_eksik_girdi_ADIYLA_soyleniyor(self):
        """Beyan gerçeği söylemeli: hangi yol eksik, nereden gelir."""
        p = _restore_kos(True, False)
        # Eksik olan ADIYLA listelenmeli; DOLU olan listeye girmemeli.
        madde_blogu = p.stdout.split('PAKETLEME YAPMA.')[-1].split(
            'Girdiler depoda tutulmaz')[0]
        assert 'packaging/mac/libs' in madde_blogu
        assert 'packaging/win/payload' not in madde_blogu
        assert 'dizin YOK' in madde_blogu


# ---------------------------------------------------------------------------
# P10B4-13 — build_sky_assets._indir önbellek isabetinde imzayı sormuyordu
# ---------------------------------------------------------------------------
class TestP10B4_13OnbellekImzasi:
    @staticmethod
    def _bsa():
        sys.path.insert(0, str(ROOT / 'tools' / 'sky_assets'))
        import build_sky_assets
        return build_sky_assets

    def test_imzasi_bozuk_onbellek_reddedilir_ve_silinir(self, tmp_path,
                                                         capsys):
        bsa = self._bsa()
        hedef = tmp_path / 'bozuk.tif'
        hedef.write_bytes(b'<!DOCTYPE html>' + b'x' * 4096)
        # Ağ yok: doğru davranış imzayı görüp dosyayı silmek ve indirmeye
        # düşmektir (indirme de bu ortamda yükselir). Kusurlu davranış
        # sessizce 'geçerli önbellek' deyip dönmekti.
        with pytest.raises(Exception):
            bsa._indir('https://gecersiz.hrma.ornek/asla',
                       hedef, en_az_bayt=1024, imza=b'II*\x00')
        assert not hedef.exists(), (
            'imzası tutmayan önbellek dosyası SİLİNMEDİ — sonraki koşumda '
            'yine "geçerli" sayılacak')

    def test_imzasi_dogru_onbellek_kullanilir(self, tmp_path):
        """Yanlış-kapanma ikizi: sağlam önbellek yeniden indirilmez."""
        bsa = self._bsa()
        hedef = tmp_path / 'iyi.tif'
        hedef.write_bytes(b'II*\x00' + b'y' * 4096)
        yol = bsa._indir('https://gecersiz.hrma.ornek/asla',
                         hedef, en_az_bayt=1024, imza=b'II*\x00')
        assert yol == hedef and hedef.exists()

    def test_docstring_iddiasinin_kod_karsiligi_var(self):
        """'tutmazsa dosyayı SİLER' iddiası koda bağlı mı?"""
        kaynak = (ROOT / 'tools' / 'sky_assets'
                  / 'build_sky_assets.py').read_text(encoding='utf-8')
        govde = kaynak.split('def _indir(')[1].split('\ndef ')[0]
        assert 'unlink()' in govde, (
            'docstring SİLER diyor ama _indir hiçbir yerde dosya silmiyor')


# ---------------------------------------------------------------------------
# P10B4-04 — wiring_map giriş sayfası ile detay sayfası aynı büyüklük için
# farklı sayı basıyordu (üretimde 284 ⟷ 87, 3,26×)
# ---------------------------------------------------------------------------
class _SahteRapor:
    """Ürünün kendi yaprak biçimi: dizi elemanları ``[i]`` indisiyle gelir."""

    def __init__(self, seri_sayisi=3, ornek=40, tekil=7):
        self.constant_outputs = []
        for s in range(seri_sayisi):
            for i in range(ornek):
                self.constant_outputs.append('.seri%d.deger[%d]' % (s, i))
        for t in range(tekil):
            self.constant_outputs.append('.motor.magic_%d' % t)
        self.baseline_leaves = {y: 3.14159 for y in self.constant_outputs}
        self.baseline_leaf_count = len(self.baseline_leaves)
        self.live_inputs = ['a', 'b']
        self.dead_inputs = ['d']
        self.echo_only_inputs = ['e']
        self.unmeasurable = []
        self.declared_but_live = []
        self.changed_paths = {'a': ['.motor.thrust_n']}
        # ÖH D20 · P10B4-06 — harita artık seçim kapsamını da yayımlıyor
        # (``secimKapsami`` / ``kismenOlculdu``). Test çifti sözleşmenin
        # TAMAMINI modellemeli; eksik alan bırakmak ``build_html``i
        # hoşgörülü yazmaya (sessiz varsayılan) zorlardı.
        self.secim_kapsami = {'b': {'toplam': 4, 'denenen': 1,
                                    'taban_secenek': 'x',
                                    'denenen_secenek': 'y'}}
        self.kismen_olculdu = {}

    def summary(self):
        return 'sahte'


class TestP10B4_04HaritaTekSayi:
    @staticmethod
    def _sayfalar(rapor):
        import re
        import wiring_map
        tmap = {'a': 'thrust', 'b': 'pc', 'd': 'x', 'e': 'y'}
        detay = wiring_map.build_html('hybrid', rapor, None, tmap, '—')
        giris = wiring_map.build_index(
            [('hybrid', pathlib.Path('wiring_map_hybrid.html'), rapor)], '—')
        # ÖH D19 · P10B4-07 — meta satırı GENİŞLEDİ: sabit sayısının yanına
        # artık erime hükmü de yazılıyor
        # ("... N sabit (M sınıflandırılmamış · erime ÖLÇÜLMEDİ ...)").
        # Bu sınıfın koruduğu sözleşme (giriş ve detay AYNI sayıyı basar)
        # değişmedi; yalnız desen kapanış parantezine kadar okuyordu.
        d = re.search(r'(\d+) sabit\s*\((\d+) sınıflandırılmamış', detay)
        gk = re.search(
            r'<span class="(?:ok|bad)">(\d+) sınıflandırılmamış</span>', giris)
        gt = re.search(r'Toplam sınıflandırılmamış: <b>(\d+)</b>', giris)
        # ÖH D23 · P15B3-09 — KART ÜÇ SAYI BASIYOR. Sınıflandırma
        # "açıklandı" ile "aklandı"yı ayırdı: ``sablon_koru`` ve
        # ``girdi_yankisi`` ölçümle AÇIKLANMIŞ ama AKLANMAMIŞ kalemlerdir
        # ve kendi rozetlerinde durur. Bu sınıfın koruduğu sözleşme
        # (giriş ve detay AYNI sayıyı basar) değişmedi; sözcük değişti ve
        # toplam denklemine üçüncü terim girdi.
        ga = re.search(r'<span>(\d+) sabit aklandı</span>', giris)
        gac = re.search(r'<span class="(?:ok|amb)">(\d+) açık hesap</span>',
                        giris)
        assert d and gk and gt and ga and gac, \
            'sayfa biçimi değişmiş, ölçüm okunamadı'
        return {'detay_sabit': int(d.group(1)),
                'detay_belirsiz': int(d.group(2)),
                'giris_belirsiz': int(gk.group(1)),
                'giris_toplam_belirsiz': int(gt.group(1)),
                'giris_acik_hesap': int(gac.group(1)),
                'giris_aciklanan': int(ga.group(1))}

    def test_iki_sayfa_ayni_sayiyi_basar(self):
        import wiring_map
        rapor = _SahteRapor()
        s = self._sayfalar(rapor)
        katlanmis = len({wiring_map.collapse(y)
                         for y in rapor.constant_outputs})
        ham = len(rapor.constant_outputs)
        assert ham != katlanmis, 'ölçüm anlamsız: fikstürde katlanacak dizi yok'
        assert s['giris_belirsiz'] == s['detay_belirsiz'], (
            'giriş sayfası %d, detay sayfası %d diyor — "izlenen tek sayı" '
            'iki yerde iki farklı şey' % (s['giris_belirsiz'],
                                          s['detay_belirsiz']))
        assert s['giris_toplam_belirsiz'] == s['detay_belirsiz']

    def test_sayilar_KATLANMIS_yaprak_uzerinden(self):
        """Hangi tanım kazandı: harita katlanmış yolu gösterir, sayı da öyle."""
        import wiring_map
        rapor = _SahteRapor()
        s = self._sayfalar(rapor)
        katlanmis = len({wiring_map.collapse(y)
                         for y in rapor.constant_outputs})
        assert s['detay_sabit'] == katlanmis
        assert (s['giris_belirsiz'] + s['giris_aciklanan']
                + s['giris_acik_hesap']) == katlanmis, (
            'kart toplamı (%d + %d + %d) katlanmış yaprak sayısı (%d) değil'
            % (s['giris_belirsiz'], s['giris_aciklanan'],
               s['giris_acik_hesap'], katlanmis))

    def test_tek_tanim_yeri(self):
        """İki üretici de aynı fonksiyondan okumalı (kural 4: tek kaynak)."""
        kaynak = (ROOT / 'tools' / 'wiring_map.py').read_text(encoding='utf-8')
        idx = kaynak.split('def build_index(')[1]
        assert 'sabit_sinif_ozeti(' in idx
        assert 'siniflandir_hepsi(' not in idx, (
            'giriş sayfası sınıflandırmayı yine kendi başına çağırıyor')
        html_govde = kaynak.split('def build_html(')[1].split(
            '\ndef build_index(')[0]
        assert 'sabit_sinif_ozeti(' in html_govde
        assert 'siniflandir_hepsi(' not in html_govde


# ---------------------------------------------------------------------------
# P10B3-14 — kapının canlı duman testi SABİT 8087 kullanıyordu ve cevabı
# verenin KENDİ süreci olduğunu sınamıyordu
# ---------------------------------------------------------------------------
KAPI = ROOT / 'packaging' / 'release_gate.sh'


class TestP10B3_14DumanTestiPortu:
    @staticmethod
    def _kaynak():
        return KAPI.read_text(encoding='utf-8')

    def test_port_cekirdekten_secilir(self):
        """Sabit port yok: 0'a bağlanıp çekirdeğin verdiği port kullanılır."""
        k = self._kaynak()
        assert "s.bind(('127.0.0.1', 0))" in k, (
            'duman testi portu hâlâ sabit — yabancı bir sunucu kapıyı '
            'geçirebilir')
        assert 'getsockname' in k

    def test_baslamadan_once_portun_bos_oldugu_olculur(self):
        k = self._kaynak()
        assert 'connect_ex' in k, 'port dolu mu diye SORULMUYOR'
        assert 'BAŞKASI tarafından tutuluyor' in k, (
            'port doluysa kapı düşmüyor')

    def test_hazir_olma_dongusu_kendi_surecini_sorar(self):
        k = self._kaynak()
        blok = k.split('DUMAN_SONUC=1')[1].split('elif')[0]
        assert 'kill -0 "$SUNUCU_PID"' in blok, (
            'hazır-olma yoklaması cevabı verenin KENDİ süreci olduğunu '
            'sınamıyor — 8087 sınıfı kusur geri gelir')
        assert 'ÖLDÜ' in k

    def test_kapi_kabuk_sozdizimi_gecerli(self):
        p = subprocess.run(['bash', '-n', str(KAPI)], capture_output=True,
                           text=True, timeout=60)
        assert p.returncode == 0, p.stderr

    def test_bos_port_secici_gercekten_bos_port_veriyor(self):
        """Kapıdaki seçicinin AYNISI koşturulur: verdiği port bağlanabilir mi?

        (Betiğin tamamı 15+ dk sürer; ölçülen şey seçicinin kendisidir.)
        """
        import socket
        k = self._kaynak()
        govde = k.split('PORT="$("$PY" - <<\'PY\'\n')[1].split('\nPY\n')[0]
        ortam: dict = {}
        import io
        import contextlib
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            exec(compile(govde, '<kapi>', 'exec'), ortam)
        port = int(cikti.getvalue().strip())
        assert 1024 < port < 65536
        s = socket.socket()
        try:
            s.bind(('127.0.0.1', port))   # boş olmalı
        finally:
            s.close()


# ---------------------------------------------------------------------------
# P10B3-06 — run_windows.py eksik paketleri SÜRÜMSÜZ kuruyordu
# ---------------------------------------------------------------------------
class TestP10B3_06WindowsKurulumuPinli:
    @staticmethod
    def _kaynak():
        return (ROOT / 'hrma' / 'run_windows.py').read_text(encoding='utf-8')

    def test_surumsuz_pip_install_kalmadi(self):
        import re
        govde = self._kaynak().split('def install_missing_packages(')[1].split(
            '\ndef ')[0]
        assert not re.search(r'"install",\s*package', govde), (
            'paketler hâlâ tek tek ve SÜRÜMSÜZ kuruluyor — numpy<2 pini '
            'aşılır')
        assert '"-r", REQUIREMENTS' in govde or "'-r', REQUIREMENTS" in govde

    def test_requirements_yoksa_fail_closed(self, tmp_path, monkeypatch):
        """Liste yoksa sürümsüz kuruluma DÜŞÜLMEZ; False döner."""
        import importlib
        sys.path.insert(0, str(ROOT))
        mod = importlib.import_module('hrma.run_windows')
        monkeypatch.setattr(mod, 'REQUIREMENTS',
                            str(tmp_path / 'yok.txt'))
        cagrildi = []
        monkeypatch.setattr(mod.subprocess, 'check_call',
                            lambda *a, **k: cagrildi.append(a))
        assert mod.install_missing_packages(['numpy']) is False
        assert not cagrildi, 'requirements yokken yine de pip çağrıldı'

    def test_requirements_yolu_depo_kokunu_gosteriyor(self):
        import importlib
        sys.path.insert(0, str(ROOT))
        mod = importlib.import_module('hrma.run_windows')
        assert pathlib.Path(mod.REQUIREMENTS) == ROOT / 'requirements.txt'
        assert pathlib.Path(mod.REQUIREMENTS).is_file()


# ---------------------------------------------------------------------------
# P10B3-24 — kaynak kurulumu kullanıcının GENEL Python'una kuruyordu
# ---------------------------------------------------------------------------
class TestP10B3_24IzoleOrtam:
    @staticmethod
    def _kaynak():
        return (ROOT / 'start.sh').read_text(encoding='utf-8')

    def test_kurulum_sanal_ortama_yapilir(self):
        k = self._kaynak()
        assert '-m venv "$VENV_DIR"' in k, 'sanal ortam kurulmuyor'
        assert '"$VENV_PY" -m pip install --prefer-binary -r requirements.txt' in k

    def test_kosum_da_ayni_ortamdan(self):
        """Kurulum bir yere, koşum başka yere olursa kurulum boşa gider."""
        k = self._kaynak()
        assert '"$VENV_PY" hrma/run.py' in k
        assert '$PYTHON_CMD hrma/run.py' not in k

    def test_pip_yukseltmesi_her_acilista_kosmuyor(self):
        k = self._kaynak()
        blok = k.split('if [ "$VENV_YENI" = "1" ]; then')[1].split('fi')[0]
        assert 'pip install --upgrade pip' in blok, (
            'pip yükseltmesi ortam-ilk-kurulum koşuluna bağlı değil')
        # Koşulun DIŞINDA kalan bir yükseltme olmamalı (yorum satırları hariç)
        kodlar = [s for s in k.splitlines()
                  if 'pip install --upgrade pip' in s
                  and not s.strip().startswith('#')]
        assert len(kodlar) == 1, kodlar

    def test_venv_kurulamazsa_genel_pythona_DUSULMEZ(self):
        k = self._kaynak()
        blok = k.split('if ! $PYTHON_CMD -m venv "$VENV_DIR"; then')[1].split(
            '\n    fi')[0]
        assert 'exit 1' in blok, 'venv kurulamayınca sessizce devam ediliyor'
        assert 'pip install' not in blok

    def test_kotu_tavsiye_kalmadi(self):
        """`sudo pip install` / `--user` önerileri genel Python'a iter."""
        k = self._kaynak()
        assert 'sudo $PYTHON_CMD -m pip install' not in k
        assert '--user flask' not in k

    def test_venv_depoya_girmez(self):
        yoksay = (ROOT / '.gitignore').read_text(encoding='utf-8')
        assert '.venv/' in yoksay

    def test_start_sh_sozdizimi_gecerli(self):
        p = subprocess.run(['bash', '-n', str(ROOT / 'start.sh')],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr

    # -- Windows yarısı (OH D33; kalemin notu "start.bat değişikliği gerekir"
    #    diyordu). start.sh D18'de onarıldı, start.bat aynı kusurla kalmıştı:
    #    kurulum kullanıcının GENEL Python'una gidiyor, her açılışta pip
    #    yükseltiliyor ve pip yoksa ensurepip ile genel Python değiştiriliyordu.

    @staticmethod
    def _bat():
        return (ROOT / 'start.bat').read_text(encoding='utf-8')

    @staticmethod
    def _bat_kod_satirlari():
        """Yorum (REM) ve echo satırları ÇIKARILMIŞ gerçek komut satırları.

        Bekçinin metne değil DAVRANIŞA bakması için: kusuru anlatan bir REM
        satırı ya da kullanıcıya bilgi veren bir echo, kusurun kendisi
        sayılmamalı (D33 dersi: şablon-körü bekçi).
        """
        satirlar = []
        for ham in TestP10B3_24IzoleOrtam._bat().splitlines():
            s = ham.strip()
            if not s:
                continue
            if s.upper().startswith('REM ') or s.startswith('::'):
                continue
            if s.lower().startswith('echo'):
                continue
            satirlar.append(s)
        return satirlar

    def test_windows_kurulum_sanal_ortama_yapilir(self):
        k = self._bat()
        assert '-m venv "!VENV_DIR!"' in k, 'sanal ortam kurulmuyor'
        assert '"!VENV_PY!" -m pip install --prefer-binary -r requirements.txt' in k

    def test_windows_kosum_da_ayni_ortamdan(self):
        """Kurulum bir yere, koşum başka yere olursa kurulum boşa gider."""
        k = self._bat()
        assert '"!VENV_PY!" hrma\\run_windows.py' in k
        assert '"!VENV_PY!" hrma\\run.py' in k
        kodlar = [s for s in self._bat_kod_satirlari()
                  if '!PYTHON_CMD! hrma\\' in s]
        assert not kodlar, kodlar

    def test_windows_genel_pythona_YAZAN_komut_kalmadi(self):
        """PYTHON_CMD yalnız ÖLÇER (sürüm, venv varlığı); kurmaz.

        Ölçülen eski hâl: `!PYTHON_CMD! -m pip install --upgrade pip`,
        `!PYTHON_CMD! -m pip install -r requirements.txt` ve
        `!PYTHON_CMD! -m ensurepip --upgrade` — üçü de kullanıcının genel
        Python'unu değiştiriyordu.
        """
        for s in self._bat_kod_satirlari():
            assert '!PYTHON_CMD! -m pip install' not in s, s
            assert '-m ensurepip' not in s, s

    def test_windows_pip_yukseltmesi_her_acilista_kosmuyor(self):
        k = self._bat()
        kodlar = [s for s in self._bat_kod_satirlari()
                  if 'pip install --upgrade pip' in s]
        assert len(kodlar) == 1, kodlar
        blok = k.split('if "!VENV_YENI!"=="1" (')[1].split('\n)')[0]
        assert 'pip install --upgrade pip' in blok, (
            'pip yükseltmesi ortam-ilk-kurulum koşuluna bağlı değil')

    def test_windows_venv_kurulamazsa_genel_pythona_DUSULMEZ(self):
        k = self._bat()
        blok = k.split('!PYTHON_CMD! -m venv "!VENV_DIR!"')[1].split('\n    set VENV_YENI=1')[0]
        assert 'exit /b 1' in blok, 'venv kurulamayınca sessizce devam ediliyor'
        assert 'pip install' not in blok

    def test_windows_venv_kurulup_yorumlayici_YOKSA_da_duruyor(self):
        """`venv` hata döndürmese bile yorumlayıcı yerinde değilse durulur.

        Aksi hâlde bundan sonraki her komut sessizce boş bir yola giderdi.
        """
        k = self._bat()
        # İkinci 'if not exist "!VENV_PY!"' bloğu (birincisi kurulum bloğu).
        parcalar = k.split('if not exist "!VENV_PY!" (')
        assert len(parcalar) == 3, 'yorumlayıcı varlık kapısı tek (ikinci kapı yok)'
        assert 'exit /b 1' in parcalar[2].split('\n)')[0]

    def test_windows_venv_modulu_yoksa_ADIYLA_reddediliyor(self):
        """Fail-closed: venv yoksa ensurepip ile genel Python'a dokunulmaz."""
        k = self._bat()
        assert '!PYTHON_CMD! -c "import venv"' in k
        blok = k.split('!PYTHON_CMD! -c "import venv"')[1].split('\n)')[0]
        assert 'exit /b 1' in blok
        assert 'venv' in blok.lower()

    def test_windows_bat_blok_parantezleri_dengeli(self):
        """Kaba sözdizimi kapısı: cmd.exe yok, en azından blok dengesi ölçülür.

        `bash -n start.sh` karşılığı bir denetleyici macOS'ta yok; bu yüzden
        yalnız komut satırlarındaki açılan/kapanan parantez sayısı ölçülür.
        Batch'te kaçırılmış bir `)` bütün betiği sessizce bozar.
        """
        acik = 0
        for s in self._bat_kod_satirlari():
            # echo satırları zaten elendi; kalanlarda ^( kaçışı beklenmiyor
            acik += s.count('(') - s.count(')')
        assert acik == 0, 'blok parantezleri dengesiz: %d' % acik


# ---------------------------------------------------------------------------
# P10B3-10 (KISMEN) — constants.py "magic-number tutarsızlıkları bu modül
# üzerinden önlenir" diyor; g_0 / R_universal literalleri hâlâ bağımsız
# tanımlanıyordu.
#
# ÖLÇÜLDÜ (olcum_acilmayanlar.json, AST taraması): hrma/ içinde
# constants.py DIŞINDA 2 g_0 + 3 R_universal bağımsız float ataması vardı.
# Bu dalgada KARDEŞ DAL DOKUNMAYAN ikisi merkezî tanıma bağlandı:
#   hrma/analysis/heat_transfer_analysis.py  (R_UNIVERSAL + self.g0)
#   hrma/data/propellants_db.py              (UNIVERSAL_GAS_CONSTANT)
# ENGELLİ kalanlar (D18'de kardeş dal aynı dosyayı yazıyor):
#   hrma/analysis/six_dof_trajectory.py G0        -> termo-ucus
#   hrma/analysis/acoustic_modes.py R_UNIVERSAL.. -> kati
#   hrma/data/external_data_fetcher.py 8314.5     -> ihracat (DEĞER FARKLI!)
#   hrma/constants.py'nin kendisi                 -> fizik
# ---------------------------------------------------------------------------
class TestP10B3_10TekTanimNoktasi:
    def test_isi_transferi_merkezi_sabitleri_kullanir(self):
        from hrma import constants
        from hrma.analysis import heat_transfer_analysis as hta
        assert hta.R_UNIVERSAL is constants.R_UNIVERSAL

    def test_yakit_veritabani_merkezi_sabiti_kullanir(self):
        from hrma import constants
        from hrma.data import propellants_db
        assert propellants_db.UNIVERSAL_GAS_CONSTANT is constants.R_UNIVERSAL

    def test_bu_iki_dosyada_literal_kalmadi(self):
        import ast
        for rel in ('hrma/analysis/heat_transfer_analysis.py',
                    'hrma/data/propellants_db.py'):
            agac = ast.parse((ROOT / rel).read_text(encoding='utf-8'))
            for d in ast.walk(agac):
                if isinstance(d, (ast.Assign, ast.AnnAssign)):
                    v = d.value
                    if isinstance(v, ast.Constant) and isinstance(
                            v.value, float):
                        assert v.value not in (9.80665, 9.81, 8314.462618,
                                               8314.5, 8314.0), (
                            '%s:%d hâlâ bağımsız sabit tanımlıyor: %r'
                            % (rel, d.lineno, v.value))

    def test_degerler_degismedi(self):
        """Bu bir TEK-TANIM göçüdür, sayı göçü DEĞİL: değerler aynı."""
        from hrma import constants
        assert constants.R_UNIVERSAL == 8314.462618
        assert constants.G_0 == 9.80665
