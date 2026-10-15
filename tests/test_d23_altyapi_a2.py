"""ÖH D23 · altyapi · aşama-2 — onarılan kalemlerin bekçileri.

Her sınıf BİR defter kalemine bağlıdır ve o kalemin ÖLÇÜLMÜŞ kusurunu
görür. Ters-mutasyon kanıtları
``docs/scofield/raw/OH/D23/altyapi/a2/mutasyon.json`` içindedir: her
bekçi, onarımı geçici olarak geri alındığında KIRMIZI verdiği
gösterilerek bağlanmıştır.

Ölçüm gövdesi: ``docs/scofield/raw/OH/D23/altyapi/a2/olcum.py``
(önce.json ⟷ sonra.json).
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from tests.support.kanit import kanit_gerekli

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from tools.browser_harness import esikler, sayfalar, tur  # noqa: E402


def _yukle(ad: str, yol: Path):
    spec = importlib.util.spec_from_file_location(ad, yol)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _fonksiyon_kaynagi(metin: str, ad: str) -> str:
    agac = ast.parse(metin)
    satirlar = metin.splitlines()
    for d in ast.walk(agac):
        if isinstance(d, ast.FunctionDef) and d.name == ad:
            return '\n'.join(satirlar[d.lineno - 1:d.end_lineno])
    return ''


# ===========================================================================
# P10B4-17 — build_launch_site_assets.py indirdiğini KANITLIYOR mu?
# ===========================================================================

class TestP10B417IndirmeKaniti:
    """ÖLÇÜLDÜ (once.json): ``_download``\'ın kanıt sayısı 0/4 idi.

    HTTP kodu sorulmuyordu, boyut sorulmuyordu, içerik sorulmuyordu ve
    önbellek ölçütü ``st_size > 0`` idi — yani bir kez inen 12 baytlık HTML
    hata sayfası sonsuza dek "geçerli önbellek" sayılıyordu.
    """

    BETIK = KOK / 'tools' / 'build_launch_site_assets.py'

    @pytest.fixture(scope='class')
    def modul(self):
        return _yukle('bla', self.BETIK)

    def test_indirme_ucunu_de_soruyor(self, modul):
        kaynak = _fonksiyon_kaynagi(self.BETIK.read_text(encoding='utf-8'),
                                    '_download')
        assert kaynak, '_download bulunamadı'
        assert re.search(r'\.status\b', kaynak), 'HTTP kodu sorulmuyor'
        assert 'en_az_bayt' in kaynak, 'boyut sorulmuyor'
        assert 'imza' in kaynak, 'içerik imzası sorulmuyor'

    def test_her_indirme_cagrisi_kanit_parametresi_tasiyor(self):
        metin = self.BETIK.read_text(encoding='utf-8')
        cagrilar = re.findall(r'_download\(([^)]*)\)', metin, re.S)
        # Tanımın kendisi hariç; her ÇAĞRI dört argüman almalı.
        cagrilar = [c for c in cagrilar if 'dest: Path' not in c]
        assert cagrilar, 'çağrı bulunamadı'
        for c in cagrilar:
            assert c.count(',') >= 3, c

    def test_http_200_disi_yukselir(self, modul, tmp_path, monkeypatch):
        class SahteYanit:
            status = 503
            headers = {'Content-Type': 'text/html'}

            def read(self):
                return b'\xff\xd8\xff' + b'x' * 10_000_000

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(modul.urllib.request, 'urlopen',
                            lambda *a, **k: SahteYanit())
        with pytest.raises(RuntimeError, match='HTTP 503'):
            modul._download('http://x/y.jpg', tmp_path / 'y.jpg',
                            modul.BLUE_MARBLE_EN_AZ_BAYT, modul.JPEG_IMZA)
        assert not (tmp_path / 'y.jpg').exists(), 'kanıtsız dosya yazıldı'

    def test_kucuk_govde_yukselir(self, modul, tmp_path, monkeypatch):
        class SahteYanit:
            status = 200
            headers = {'Content-Type': 'text/html'}

            def read(self):
                return b'<html>404</html>'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(modul.urllib.request, 'urlopen',
                            lambda *a, **k: SahteYanit())
        with pytest.raises(RuntimeError, match='SAHTE VARLIK'):
            modul._download('http://x/y.jpg', tmp_path / 'y.jpg',
                            modul.BLUE_MARBLE_EN_AZ_BAYT, modul.JPEG_IMZA)

    def test_imzasiz_govde_yukselir(self, modul, tmp_path, monkeypatch):
        class SahteYanit:
            status = 200
            headers = {'Content-Type': 'text/html'}

            def read(self):
                return b'<html>' + b'x' * 10_000_000

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(modul.urllib.request, 'urlopen',
                            lambda *a, **k: SahteYanit())
        with pytest.raises(RuntimeError, match='imza'):
            modul._download('http://x/y.jpg', tmp_path / 'y.jpg',
                            modul.BLUE_MARBLE_EN_AZ_BAYT, modul.JPEG_IMZA)

    def test_bozuk_onbellek_reddedilir_ve_silinir(self, modul, tmp_path,
                                                  monkeypatch):
        """Eski kusurun tam kalbi: boyutu yeten AMA imzası tutmayan önbellek."""
        hedef = tmp_path / 'y.jpg'
        hedef.write_bytes(b'<html>' + b'x' * 10_000_000)   # boyut YETİYOR
        cagrildi = {'n': 0}

        class SahteYanit:
            status = 200
            headers = {'Content-Type': 'image/jpeg'}

            def read(self):
                cagrildi['n'] += 1
                return b'\xff\xd8\xff' + b'x' * 10_000_000

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(modul.urllib.request, 'urlopen',
                            lambda *a, **k: SahteYanit())
        modul._download('http://x/y.jpg', hedef,
                        modul.BLUE_MARBLE_EN_AZ_BAYT, modul.JPEG_IMZA)
        assert cagrildi['n'] == 1, 'bozuk önbellek "geçerli" sayıldı'
        assert hedef.read_bytes().startswith(b'\xff\xd8\xff')


# ===========================================================================
# P13B1-11 — canlı duman testi GÖVDEYİ sınıyor mu?
# ===========================================================================

KAPI = _yukle('duman_kapisi', KOK / 'tools' / 'duman_govde_kapisi.py')


class TestP13B111DumanGovdesi:
    """ÖLÇÜLDÜ (once.json): gövdeye bakan karar sayısı 0 idi.

    ``release.yml`` yalnız ``$KOD`` = 200/403 karşılaştırması yapıyordu;
    gövde SADECE hata mesajında ``head -c 200`` ile anılıyordu.
    """

    YML = KOK / '.github' / 'workflows' / 'release.yml'

    def test_yml_ayristirilabilir(self):
        """ÖH D24 / OH-D23-01: gövde İDDİASIZDI.

        ``safe_load`` boş dosyada da ``None`` döndürür ve hata vermez;
        iş akışı tamamen silinse bile test yeşil kalırdı. Ayrıştırmanın
        BİR İŞ AKIŞI ürettiği artık sınanıyor.
        """
        import yaml
        belge = yaml.safe_load(self.YML.read_text(encoding='utf-8'))
        assert isinstance(belge, dict) and belge, (
            '%s boş ayrıştı — iş akışı yok' % self.YML.name)
        assert belge.get('jobs'), 'iş akışında "jobs" yok'
        for ad, is_ in belge['jobs'].items():
            assert is_.get('steps'), '%s işinin adımı yok' % ad

    def test_duman_adimi_govde_kapisini_cagiriyor(self):
        metin = self.YML.read_text(encoding='utf-8')
        blok = metin.split('Canlı duman testi', 1)[1]
        blok = re.split(r'\n      - name: ', blok, maxsplit=1)[0]
        assert 'duman_govde_kapisi.py' in blok
        # Üç motorun üçü için de alan listesi tanımlı mı?
        for ad in ('ALAN_HIBRIT', 'ALAN_KATI', 'ALAN_SIVI'):
            assert ad in blok, ad
        assert 'gövde hüküm taşımıyor' in blok

    def test_alan_yollari_uc_motorda_da_gercek(self):
        """Kapı UYDURMA alan adı sınamaz: yollar canlı yanıttan alındı."""
        metin = self.YML.read_text(encoding='utf-8')
        assert "ALAN_HIBRIT='motor.c_star" in metin
        assert "ALAN_KATI='c_star" in metin
        assert "ALAN_SIVI='c_star" in metin

    def test_bos_govde_kalir(self):
        assert KAPI.govde_hukmu({}, ['c_star'])[0] is False

    def test_govde_nesne_degilse_kalir(self):
        assert KAPI.govde_hukmu([1, 2], ['c_star'])[0] is False

    def test_alan_listesi_bossa_kalir(self):
        """FAIL-CLOSED: ölçüm yapılmaması "temiz geçiş" değildir."""
        assert KAPI.govde_hukmu({'c_star': 1.0}, [])[0] is False

    @pytest.mark.parametrize('deger', [0, -1.0, float('nan'), float('inf'),
                                       True, 'çok', None])
    def test_sayi_olmayan_ve_pozitif_olmayan_deger_kalir(self, deger):
        assert KAPI.govde_hukmu({'c_star': deger}, ['c_star'])[0] is False

    def test_saglikli_govde_gecer(self):
        gecti, ozet = KAPI.govde_hukmu(
            {'motor': {'c_star': 1613.1, 'throat_diameter': 0.0435,
                       'chamber_temperature': 3369.7}},
            ['motor.c_star', 'motor.throat_diameter',
             'motor.chamber_temperature'])
        assert gecti is True
        assert 'c_star=1613.1' in ozet

    def test_betik_cikis_kodu_kaldi_demeyi_biliyor(self, tmp_path):
        yol = tmp_path / 'g.json'
        yol.write_text('{"c_star": 0}', encoding='utf-8')
        r = subprocess.run(
            [sys.executable, str(KOK / 'tools' / 'duman_govde_kapisi.py'),
             str(yol), 'c_star'], capture_output=True, text=True)
        assert r.returncode == 1
        assert 'kesin pozitif değil' in r.stdout


# ===========================================================================
# P10B3-19 — paketlenen bağımlılıklar TEK KAYNAKTAN okunabiliyor mu?
# ===========================================================================

BUNDLE_KAPISI = _yukle('bundle_kapisi', KOK / 'tools' / 'bundle_kapisi.py')


class TestP10B319BundleTekKaynak:
    """ÖLÇÜLDÜ (once.json): 5 paket yalnız requirements.txt'te ve BEŞİ DE
    beyansızdı; bunlardan ``rocketcea`` aslında PAKETE GİRİYORDU (win:
    build_win_payload.sh --no-deps, mac: build_mac_app.sh anaconda kopyası).
    Manifest eksik değil, YANILTICIYDI."""

    def test_kapi_bugun_aciktir(self):
        sonuc = BUNDLE_KAPISI.denetle()
        assert sonuc['beyansiz_eksik'] == [], sonuc['beyansiz_eksik']
        assert sonuc['celisen_kisit'] == [], sonuc['celisen_kisit']
        assert sonuc['betikle_caprazlanmayan_asama2'] == []
        assert sonuc['gecti'] is True

    def test_rocketcea_artik_BEYANLI(self):
        """Kalemin adı konmuş paketi: pakete giriyor ama manifestte yoktu."""
        metin = (KOK / 'packaging' / 'requirements_bundle.txt').read_text(
            encoding='utf-8')
        asama2, haric = BUNDLE_KAPISI.beyanlari_coz(metin)
        assert 'rocketcea' in asama2
        assert asama2['rocketcea']['gerekce'].strip()

    def test_her_beyanin_gerekcesi_var(self):
        metin = (KOK / 'packaging' / 'requirements_bundle.txt').read_text(
            encoding='utf-8')
        asama2, haric = BUNDLE_KAPISI.beyanlari_coz(metin)
        assert len(asama2) >= 4 and len(haric) >= 4
        for kayit in asama2.values():
            assert kayit['gerekce'].strip()
        for gerekce in haric.values():
            assert gerekce.strip()

    def test_beyansiz_eksik_kapiyi_kapatir(self, monkeypatch):
        """Ters yön: beyan silinirse kapı KAPANMALI."""
        gercek = BUNDLE_KAPISI.BUNDLE.read_text(encoding='utf-8')
        kirpik = '\n'.join(ln for ln in gercek.splitlines()
                           if 'rocketcea' not in ln)
        monkeypatch.setattr(
            BUNDLE_KAPISI, 'BUNDLE',
            type('S', (), {'read_text': staticmethod(lambda **k: kirpik)})())
        sonuc = BUNDLE_KAPISI.denetle()
        assert 'rocketcea' in sonuc['beyansiz_eksik']
        assert sonuc['gecti'] is False

    def test_celisen_pin_yakalanir(self):
        """``==1.0`` pini ``>=2.0`` kısıtını sağlamaz."""
        tamam, gerekce = BUNDLE_KAPISI.kisiti_sagliyor('==1.0.0', '>=2.0.0')
        assert tamam is False and 'sağlamıyor' in gerekce
        assert BUNDLE_KAPISI.kisiti_sagliyor('==1.26.4', '>=1.24.0,<2')[0]
        assert not BUNDLE_KAPISI.kisiti_sagliyor('==2.1.0', '>=1.24.0,<2')[0]

    def test_asama2_beyani_betikle_caprazlanir(self, monkeypatch):
        """Manifest ile derleme betikleri sessizce ayrışamaz."""
        monkeypatch.setattr(BUNDLE_KAPISI, 'DERLEME_BETIKLERI', ())
        sonuc = BUNDLE_KAPISI.denetle()
        assert sonuc['betikle_caprazlanmayan_asama2'], (
            'betikler boşken bile çapraz "geçti" dedi')
        assert sonuc['gecti'] is False


# ===========================================================================
# P10B3-03 + P17B1-15 — Analiz Merkezi kiracı kapsamı
# ===========================================================================

#: 4 Eylül 2026 canlı sondasında /hybrid'de READY ölçülen satırlar.
CANLI_READY = ('chamber_nozzle_wall.structural', 'nozzle_flow.cfd',
               'chamber_acoustics.acoustic_modes',
               'chamber_acoustics.combustion_stability')


class TestP10B303KiraciKapsami:
    """ÖLÇÜLDÜ (once.json): tanımlı kiracı 1, canlı READY 4, kapsanan 1.

    İki kararlılık kiracısı (``acoustic_modes``, ``combustion_stability``)
    hiçbir denetim katmanına girmiyordu; JS okuyucusu ``son.data.cfd``ye
    gömülüydü, yani ikinci bir kiracı eklemek JS düzenlemeyi gerektiriyordu.
    """

    def test_iki_kararlilik_kiracisi_tanimli(self):
        adlar = {k.satir_anahtari
                 for s in sayfalar.SAYFALAR.values()
                 for k in s.merkez_kiracilari}
        assert 'chamber_acoustics.acoustic_modes' in adlar
        assert 'chamber_acoustics.combustion_stability' in adlar

    def test_canli_ready_kapsami_1den_3e_cikti(self):
        adlar = {k.satir_anahtari
                 for s in sayfalar.SAYFALAR.values()
                 for k in s.merkez_kiracilari}
        kapsanan = set(CANLI_READY) & adlar
        assert len(kapsanan) == 3, sorted(kapsanan)

    def test_kapsanmayan_ready_ADIYLA_beyan_edilmis(self):
        """FAIL-CLOSED: ölçülmemiş kiracı sessizce yok sayılmaz, ADI YAZILIR.

        ÖH D24 / P17B1-15 — BEKÇİ SAYFA BAŞINA ÇEVRİLDİ. Eski hâli
        ``/hybrid``in canlı READY listesini (``CANLI_READY``) GENEL
        beyan listesiyle (``OLCULMEMIS_HAZIR_KIRACILAR``) eşitliyordu;
        beyan üç sayfanın birleşimine dönüşünce (``/solid``da
        ``grain_section.planar_grain`` da kapsanmıyor) eşitlik yanlış
        yerden kırılırdı. Karşılaştırma artık AYNI sayfanın ölçümüne
        karşı yapılıyor — gevşeme değil, doğru eksene oturtma.
        """
        adlar = {k.satir_anahtari
                 for k in sayfalar.SAYFALAR['hybrid'].merkez_kiracilari}
        eksik = set(CANLI_READY) - adlar
        assert eksik == set(sayfalar.kapsanmayan_ready()['hybrid']), eksik
        # Beyan listesi her sayfanın kapsanmayanını KAPSAR (fail-closed).
        assert eksik <= set(sayfalar.OLCULMEMIS_HAZIR_KIRACILAR), eksik

    def test_js_okuyucusu_artik_kiraciya_gomulu_degil(self):
        kod = '\n'.join(ln for ln in tur.JS_MERKEZ_KIRACI.splitlines()
                        if not ln.strip().startswith('//'))
        assert 'son.data.cfd' not in kod
        assert 'c.yuk_anahtari' in kod and 'c.yuk_alanlari' in kod
        # CFD'ye özgü hiçbir alan adı JS gövdesinde kalmamalı.
        for ad in ('judgment_confidence', 'budget_advisory',
                   'residual_history', 'kernel_backend', 'inlet_conditioning'):
            assert ad not in kod, ad

    def test_cfd_yuk_sozlesmesi_tanimda_ve_TAM(self):
        adlar = [a[0] for a in sayfalar.CFD_KIRACISI.yuk_alanlari]
        # Eski JS gövdesinin okuduğu 12 alanın hepsi taşındı mı?
        for ad in ('converged', 'iterations', 'kernel', 'judgment_confidence',
                   'separated', 'bridge_refused', 'budget_advisory',
                   'budget_advisory_reasons', 'contraction_ratio',
                   'alan_bloklu', 'kalinti_noktalari', 'resolution'):
            assert ad in adlar, ad
        assert sayfalar.CFD_KIRACISI.yuk_anahtari == 'cfd'

    def test_kararlilik_kiracilari_yuk_okuyor(self):
        for kiraci in (sayfalar.ACOUSTIC_MODES_KIRACISI,
                       sayfalar.COMBUSTION_STABILITY_KIRACISI):
            assert kiraci.yuk_anahtari == '', kiraci.ad
            assert len(kiraci.yuk_alanlari) >= 8, kiraci.ad
            for ad, yol, donusum in kiraci.yuk_alanlari:
                assert donusum in ('deger', 'dolu_deger', 'mantiksal',
                                   'bool', 'uzunluk'), (kiraci.ad, donusum)

    def test_yapilandirma_yuk_sozlesmesini_tasiyor(self):
        gezgin = tur.SayfaGezgini.__new__(tur.SayfaGezgini)
        cfg = tur.SayfaGezgini._merkez_kiraci_yapilandirmasi(
            gezgin, sayfalar.ACOUSTIC_MODES_KIRACISI)
        assert cfg['yuk_anahtari'] == ''
        assert ['status', 'status', 'dolu_deger'] in cfg['yuk_alanlari']

    def test_hukum_rozeti_beklenen_listeye_ALINMADI(self):
        """P17B1-15 uyarısı: kampanyanın TERS ölçtüğü hüküm sabitlenmesin."""
        beklenen = sayfalar.COMBUSTION_STABILITY_KIRACISI.beklenen_imzalar
        for imza in beklenen:
            tanim = esikler.ROZET_IMZALARI[imza]
            metin = ' '.join(tanim['varyantlar'])
            assert 'STABLE' not in metin and 'KARARLI' not in metin, imza

    @pytest.mark.parametrize('imza', ['kararlilik_nozul_sonumu',
                                      'kararlilik_toplam_kayip',
                                      'kararlilik_hukum_yok',
                                      'kararlilik_besleme_ataleti'])
    def test_yeni_imzalar_urunun_kaynagina_bagli(self, imza):
        tanim = esikler.ROZET_IMZALARI[imza]
        assert tanim['varyantlar'] and tanim['sozluk_anahtarlari']
        assert tanim['gerekce'].strip()
        for dosya in tanim['kaynak_dosyalar']:
            metin = (KOK / dosya).read_text(encoding='utf-8')
            assert any(v in metin for v in tanim['varyantlar']), (imza, dosya)


# ===========================================================================
# P17B1-06 — FEA koşum eşiği ÖLÇÜYE dayanıyor mu?
# ===========================================================================

class TestP17B106EsikOlcuye:
    """ÖLÇÜLDÜ (once.json): gerekçe iki sayfayı anıyordu (hybrid, solid),
    en yavaş ölçüm olarak 0,23 s gösteriyordu ve /liquid'i HİÇ anmıyordu —
    oysa P17 kampanyası orada 117,4 s ölçtü ve kapı aynı kodda 3 koşumda
    2 kez kapanıp 1 kez açıldı."""

    def test_esik_olculen_en_yavastan_yeterince_buyuk(self):
        assert (esikler.FEA_KOSUM_ZAMAN_ASIMI_MS / 1000.0
                >= esikler.FEA_KOSUM_OLCULEN_EN_YAVAS_S
                * esikler.FEA_KOSUM_ASGARI_PAY_KATI)

    def test_dayanak_TEK_KAYNAK_ve_gerekcede_anilan(self):
        metin = (KOK / 'tools' / 'browser_harness' / 'esikler.py').read_text(
            encoding='utf-8')
        blok = metin.split('FEA_KOSUM_ZAMAN_ASIMI_MS =')[0][-4000:]
        assert 'liquid' in blok, 'en yavaş sayfa gerekçede anılmıyor'
        assert '117,4' in blok, 'ölçülen en yavaş süre gerekçede yok'
        assert 'P17B1-06' in blok

    def test_zaman_asimi_urun_kusurundan_AYRI_kaydediliyor(self):
        """Kapı yine kapanır ama gerekçesi "hüküm kazanılmadı" diye okunur."""
        metin = (KOK / 'tools' / 'browser_harness' / 'tur.py').read_text(
            encoding='utf-8')
        assert metin.count("olcum['asama'] = 'zaman_asimi'") >= 2


# ===========================================================================
# P17B4-06 — kurulu .app kendi mührünü kırıyor mu?
# ===========================================================================

class TestP17B406MuhurKorumasi:
    """ÖLÇÜLDÜ (once.json + raw/P17/B4-rapor.md): kurulu .app ilk açılışta
    mühürlü paketin içine 1654 dosya yazıyor ve ``codesign --verify``
    kurulu kopyada KALIYOR. Yazılanların ezici çoğunluğu ``__pycache__``."""

    LAUNCHER = KOK / 'packaging' / 'launcher.py'

    def test_bayt_kodu_yazimi_modul_duzeyinde_kapali(self):
        metin = self.LAUNCHER.read_text(encoding='utf-8')
        agac = ast.parse(metin)
        ust_duzey = [d for d in agac.body
                     if isinstance(d, ast.Assign)
                     and any(isinstance(t, ast.Attribute)
                             and t.attr == 'dont_write_bytecode'
                             for t in d.targets)]
        assert ust_duzey, 'sys.dont_write_bytecode modül düzeyinde kapatılmamış'

    def test_alt_sureclere_de_tasiniyor(self):
        metin = self.LAUNCHER.read_text(encoding='utf-8')
        kaynak = _fonksiyon_kaynagi(metin, '_muhru_koru')
        assert kaynak, '_muhru_koru bulunamadı'
        assert 'PYTHONDONTWRITEBYTECODE' in kaynak
        assert 'dont_write_bytecode' in kaynak

    def test_yol_kurulumundan_ONCE_cagriliyor(self):
        metin = self.LAUNCHER.read_text(encoding='utf-8')
        kaynak = _fonksiyon_kaynagi(metin, '_setup_paths')
        assert '_muhru_koru()' in kaynak
        assert kaynak.index('_muhru_koru()') < kaynak.index('addsitedir')

    def test_koruma_gercekten_calisiyor(self):
        """Alt süreçte bayrağı ölçer — iddia değil davranış."""
        kod = ('import sys, os; sys.path.insert(0, %r); '
               'import importlib.util; '
               'spec = importlib.util.spec_from_file_location("lch", %r); '
               'm = importlib.util.module_from_spec(spec); '
               'spec.loader.exec_module(m); '
               'm._muhru_koru(); '
               'print(sys.dont_write_bytecode, '
               'os.environ.get("PYTHONDONTWRITEBYTECODE"))'
               % (str(KOK), str(self.LAUNCHER)))
        r = subprocess.run([sys.executable, '-c', kod],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-800:]
        assert r.stdout.strip().endswith('True 1'), r.stdout


# ===========================================================================
# Ölçüm gövdesinin kendisi — sayı üretmeyen bekçi bekçi değildir
# ===========================================================================

class TestOlcumGovdesi:

    def test_once_json_kusuru_sayiyla_gosteriyor(self):
        once = json.loads(
            (kanit_gerekli(KOK / 'docs/scofield/raw/OH/D23/altyapi/a2/once.json'))
            .read_text(encoding='utf-8'))['olcumler']
        assert once['P10B4-17']['kanit_sayisi'] == 0
        assert once['P13B1-11']['govde_karari'] == 0
        assert once['P10B3-19']['beyansiz_eksik']
        assert once['P10B3-03/P17B1-15']['tanimli_kiraci_sayisi'] == 1
        assert once['P10B3-03/P17B1-15']['js_okuyucu_cfd_gomulu'] is True
        assert once['P17B1-06']['deger_ms'] == 180_000
        assert once['P17B4-06']['kanitlar'][
            'launcher_dontwritebytecode'] is False

    def test_curutulen_kalemler_tabanda_ZATEN_kapaliydi(self):
        """P10B3-20 ve P10B3-21: başlıkları bu ağaçta ölçümle çürütüldü.

        TARİHSEL ayak — donmuş ölçümün ne dediğini kaydeder. Ürünün BUGÜNKÜ
        hâli ayrı ölçülür (aşağıdaki ``..._bugun_de_kapali`` bekçisi);
        ikisi ayrı durur çünkü ayrı şeyler söylerler.
        """
        once = json.loads(
            (kanit_gerekli(KOK / 'docs/scofield/raw/OH/D23/altyapi/a2/once.json'))
            .read_text(encoding='utf-8'))['olcumler']
        # P10B3-20: kapının açmadığı üç sayfa TABANDA da tanımlıydı.
        for yol in ('/', '/formulas', '/launch-site'):
            assert yol in once['P10B3-20']['tanimli_yollar'], yol
        # P10B3-21: tarayıcı beyanı TABANDA da insanın özetine giriyordu.
        assert once['P10B3-21']['rapor_duzeyi_denetim'] is True
        assert once['P10B3-21']['denetim_kanali_anlatiyor'] is True
        assert once['P10B3-21']['dusus_beyani'] is True

    def test_curutulen_kalemler_BUGUN_de_kapali(self):
        """Aynı iki çürütme CANLI ağaçta da ayakta mı? — ÖH D33 / OH-UC-18.

        ÖLÇÜLDÜ (a1/once.json OH-UC-18, taban 56f88e70): yukarıdaki bekçi
        yalnız DONMUŞ ``once.json``ı okuyordu (``once_json_okuma: 1``,
        ``canli_agac_okuma: 0``). Bir çürütmenin bekçisi, kusurun GERİ
        GELEMEYECEĞİNİN kilidi olmalıdır; donmuş bir dosyayı okuyan bekçi
        ise yalnız geçmişi tekrar eder. Ürün gerilese — ``/formulas``
        turdan düşse, tarayıcı beyanı rapordan çıksa — o bekçi yeşil
        kalırdı.

        Bu ayak CANLI ağacı ölçer ve ölçütü METNE değil YAPIYA bağlar:
        ``run_tour`` içinde ``denetimler.tarayici_denetimi(...)`` çağrısının
        sonucu raporun ``'denetimler'`` anahtarına gitmeli. (Eski ölçüm
        gövdesi bunu düz dize kıyasıyla arıyordu; D26/OH-D25-02 temizliği
        çağrıyı bir değişkene aldığı için o dize BUGÜN tutmuyor —
        ``once.json``daki ``rapor_duzeyi_denetim: true`` bu yüzden bayat bir
        doğrudur. Kırılgan ölçüt burada tekrar edilmez.)
        """
        # --- P10B3-20: üç sayfa bugün de turun kapsamında ---------------
        sayfalar_metin = (KOK / 'tools/browser_harness/sayfalar.py').read_text(
            encoding='utf-8')
        canli_yollar = set(re.findall(r"yol='([^']+)'", sayfalar_metin))
        appy = (KOK / 'hrma/app.py').read_text(encoding='utf-8')
        canli_rotalar = set(re.findall(r"@app\.route\('(/[a-z\-]*)'\)", appy))
        for yol in ('/', '/formulas', '/launch-site'):
            assert yol in canli_yollar, (
                '%s görsel kapının kapsamından DÜŞMÜŞ (P10B3-20 çürütmesi '
                'artık ayakta değil): %s' % (yol, sorted(canli_yollar)))
            assert yol in canli_rotalar, (
                '%s ürün tarafında artık tanımlı değil' % yol)

        # --- P10B3-21: tarayıcı beyanı bugün de insanın özetine giriyor --
        run_tour = (KOK / 'tools/browser_harness/run_tour.py').read_text(
            encoding='utf-8')
        agac = ast.parse(run_tour)
        hukum_adlari = {
            t.id for d in ast.walk(agac) if isinstance(d, ast.Assign)
            for t in d.targets if isinstance(t, ast.Name)
            if isinstance(d.value, ast.Call)
            and getattr(d.value.func, 'attr', None) == 'tarayici_denetimi'
        }
        assert hukum_adlari, (
            'run_tour artık denetimler.tarayici_denetimi(...) çağırmıyor — '
            'rapor düzeyindeki tarayıcı beyanı düşmüş (P10B3-21)')
        rapora_giriyor = False
        for d in ast.walk(agac):
            if not isinstance(d, ast.Dict):
                continue
            for anahtar, deger in zip(d.keys, d.values):
                if (isinstance(anahtar, ast.Constant)
                        and anahtar.value == 'denetimler'
                        and hukum_adlari & {getattr(x, 'id', None)
                                            for x in ast.walk(deger)}):
                    rapora_giriyor = True
        assert rapora_giriyor, (
            'tarayıcı hükmü hesaplanıyor ama raporun "denetimler" alanına '
            'GİRMİYOR — beyan insanın özetine ulaşmıyor (P10B3-21)')

        kaynak = _fonksiyon_kaynagi(
            (KOK / 'tools/browser_harness/denetimler.py').read_text(
                encoding='utf-8'), 'tarayici_denetimi')
        assert kaynak, 'tarayici_denetimi kayıp'
        for iz, ne in (('tarayıcı: %s %s', 'denetim kanalı ne gördüğünü '
                                           'anlatmıyor'),
                       ('BEYANLI DÜŞÜŞ', 'düşüş beyanı kalkmış'),
                       ('FAIL-CLOSED', 'fail-closed künyesi kalkmış')):
            assert iz in kaynak, '%s (P10B3-21)' % ne
