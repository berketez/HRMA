"""ÖH Z5S / BEKÇİ-ÖDEME B1 — İHRAÇ VE VERİ KATMANININ KÜNYE BEKÇİSİ.

Bu dosya vaka listelemez, ÖLÇER. Sekiz defter kaleminin ONARIMI daha önce
yapıldı (Z1 ``5e059a0``, Z2 ``1957518``, Z4 ``2422558``); burada ödenen şey
onların **kapanış şartı**: onarımı KİLİTLEYEN bekçi. Ortak kusur sınıfı tektir:

    **imalata ve forma inen sayının yanındaki künye, sayının gerçekten
    cevapladığı soruyu anlatmıyordu.**

Kilitlenen sekiz yüz:

* ``P9B1-01`` (kritik) — teknik çizimdeki ``safety_factor_at_drawn_wall``
  kullanıcının SF HEDEFİNİN geri okunmasıydı (girdi 2,5 → çizim 2,5). Bugün
  çizime inen sayı çözücünün ÇİZİLEN cidarda hesapladığı ``hoop_safety_factor``
  ile BİT-AYNI, hedef ise ayrı bir alanda (``design_safety_factor_target``)
  durur. Ölçüldü (27 Ağustos 2026, ``/calculate_liquid``, inconel_718, Pc =
  100 bar, SF hedefi 2,5): boyutlandırma kolunda çizime **6,228361247485987**,
  kullanıcı 5 mm girdiğinde **15,570903118714968** iniyor — ikisi de 2,5
  DEĞİL. Sayıların kendisi malzeme/derating kararlarına bağlıdır (bkz.
  ``docs/scofield/raw/OH/Z5S/guardb1/``); bekçi sayıyı değil **kimliği**
  kilitler: çizime inen değer çözücünün ölçtüğü alanla aynı nesne olmalı ve
  hedefin ekosu OLMAMALIDIR.

* ``P9B2-07`` + ``P9B2-25`` (kritik, aynı kod yolu) — SF 0,8463 (ve kardeş
  vakada 0,103) olan bir kasa DXF'e *"verified against the pressure load"*
  damgasıyla iniyordu; yapısal analizin *"önerilen 23,18 mm"* notu ise hiçbir
  çıktıya basılmıyordu. Bu bekçi DXF'in ve PDF ölçü tablosunun **künye
  METNİNİ** kilitler: damga yalnız kazanıldığında basılır, öneri satırı hep
  basılır, 1'in altındaki katsayı gizlenmez.

* ``P9B5-05`` (kritik) — paketli PubChem anlık görüntüsünde ``htpb`` bir
  kinaz inhibitörü İLAÇ, ``polyethylene`` ALTIN idi. Deny-list ayağı ödendi;
  **anlık görüntü ayağı hâlâ açık** (aşağıdaki iki ``xfail(strict=True)``
  bunu ödenmemiş borç olarak taşır — onarıldığı gün XPASS verir).

* ``P9B5-06`` — ``liquid.html`` form alanı yalnız HÂL ÇÖZÜMLÜ değerle
  güncellenir; kategori yedeği alanı EZMEZ (şablon ezme-kapısının kendi
  bekçisi).

* ``P9B4-04`` — kriyojen depolama-durumu kapısı: LOX'un 872× vakası adıyla.

* ``P9B5-04`` — "aynı depoda iki N₂O yoğunluğu" tek, sıcaklık-parametreli
  kaynağa indi; 745 ⟷ 785 çelişkisi sıcaklık farkıdır ve künyede yazar.
  (Kanonun sıcaklık ETİKETİ kararı Berke'dedir; bekçi karar vermez, ölçer.)

* ``P9B5-25`` — jenerik yedek (800 kg/m³ + 0,001 Pa·s) susturulmadı ama
  BEYAN EDİLİR; viskozite sıralaması kullanıcı → akışkan tablosu → beyanlı
  jenerik olarak ``viscosity_basis`` alanında yazar.

ÖLÇÜM YÖNTEMİ. Üç bağımsız kanal kullanılır ve hiçbiri diğerinin kopyası
değildir: (1) çözücünün yayımladığı sözlük, (2) ihraç katmanının aynı koşuda
ürettiği DXF/PDF/çizim künyesi, (3) ``/api/get-propellant-properties`` ucunun
gövdesi. Bir künye ile onun anlattığı sayı ayrı kanallardan okunup
karşılaştırılır.

AĞ BAĞIMSIZLIĞI. Veri katmanı testleri ``HRMA_USER_DATA_DIR``i boş bir geçici
dizine bağlar (kullanıcının yerel önbelleği teste sızmasın) ve yalnız
``known_cids`` / paketli anlık görüntü ile karşılanan adları sorar; canlı
PubChem sorgusu gerektiren ad kullanılmaz.
"""

import contextlib
import io
import json
import os
import re
import tempfile

import pytest

from tests.support import form_defaults

from tests.bagimlilik_kapisi import kurulu_mu


def _coolprop_yoksa_atla(neden_gorulen):
    """Yokluk iddiası kurulum SORUSUNA dayanır (TestAtlamaGerekcesiDurust).

    CoolProp kurulu değilse atla; KURULUYKEN ürün değeri gelmediyse bu bir
    kütüphane yokluğu değil ÜRÜN KIRIĞIDIR — kırmızı yanar.
    """
    if not kurulu_mu('CoolProp'):
        pytest.skip('CoolProp bu ortamda kurulu değil (kurulum sorusuyla ölçüldü)')
    pytest.fail('CoolProp kurulu ama ürün yolu değer çözmedi: %r' % (neden_gorulen,))


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------

def _silent(fn, *args, **kwargs):
    """Çözücü/ihraç katmanının print gürültüsünü yutar."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        return fn(*args, **kwargs)


#: ``verified``ın DAMGA metni. Olumsuz künyeler bu dizeyi İÇERMEZ (metin
#: taraması yapan araç olumsuzlamayı olumlu damga sanmasın).
VERIFIED_CLAIM = 'verified against the pressure load'


# ---------------------------------------------------------------------------
# P9B1-01 — sıvı motorda ÇİZİME İNEN emniyet katsayısı hedefin ekosu değildir
# ---------------------------------------------------------------------------

SIVI_GOVDE = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'thrust': 10000,
    'chamber_pressure': 100, 'mixture_ratio': 2.5,
    'nozzle_expansion_ratio': 50, 'max_burn_duration': 400,
    'combustion_efficiency': 97, 'contraction_ratio': 4,
    'characteristic_length': 1.2, 'cooling_type': 'regenerative',
    'injector_type': 'impinging', 'engine_cycle': 'pressure_fed',
    # Kullanıcının SF HEDEFİ. Kusurun çekirdeği tam bu sayıydı: çizime
    # 2,5 iniyordu ve kardeş alan onu "user input (safety factor)" diye
    # künyeliyordu — yani çizim kullanıcının girdisini geri okuyordu.
    'safety_factor': 2.5,
    # v3.0.1 T-ÇAPA-B: basınç beslemede ``feed_pressure`` yoksa uç 422
    # ``pressure_fed_feed_pressure_not_supplied`` (L-A SV-03); sayfanın
    # gönderdiği şablon varsayılanı (tek kaynak, kopyalanmaz).
    'feed_pressure': form_defaults.sayisal_varsayilanlar('liquid')[
        'feed_pressure'],
}

#: Kullanıcının SF hedefi — çizimde AYRI alanda, ölçüm yerine geçmeden.
SF_HEDEFI = 2.5


def _sivi_kos(client, **over):
    yanit = _silent(client.post, '/calculate_liquid',
                    json=dict(SIVI_GOVDE, **over),
                    headers={'Host': '127.0.0.1:8080'})
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:400]
    return yanit.get_json()


@pytest.fixture(scope='module')
def app_client():
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def sivi_size(app_client):
    """Cidar GİRİLMEDİ -> çözücü boyutlandırır (design_mode='size')."""
    return _sivi_kos(app_client)


@pytest.fixture(scope='module')
def sivi_verify(app_client):
    """Kullanıcı 5 mm cidar girdi -> design_mode='verify'."""
    return _sivi_kos(app_client, chamber_wall_thickness=5)


def _cizim_kamarasi(motor):
    from hrma.export.cad_visualization import MotorCADDesigner
    return _silent(MotorCADDesigner()._generate_technical_drawings,
                   motor)['chamber']


class TestSiviCizimSFHedefinEkosuDegil:
    """P9B1-01: çizime inen SF, çözücünün ÖLÇTÜĞÜ alanla aynı nesnedir."""

    @pytest.mark.parametrize('kip', ('size', 'verify'))
    def test_cizilen_cidar_sf_cozucunun_olcumuyle_bit_ayni(
            self, kip, sivi_size, sivi_verify):
        motor = sivi_size if kip == 'size' else sivi_verify
        blok = motor['structural_analysis']['chamber_structure']
        cizim = _cizim_kamarasi(motor)

        olculen = blok['hoop_safety_factor']
        basilan = cizim['safety_factor_at_drawn_wall']
        assert isinstance(basilan, float), (
            f'{kip}: çizime bir SAYI inmiyor -> {basilan!r}')
        # BİT-AYNI: ihraç katmanı sayıyı yeniden türetmiyor, çözücünün
        # ÇİZİLEN cidarda hesapladığı alanı taşıyor.
        assert basilan == olculen, (
            f'{kip}: çizimdeki {basilan!r}, çözücünün ölçtüğü '
            f'{olculen!r} DEĞİL — ihraç katmanı kendi sayısını üretiyor')

    @pytest.mark.parametrize('kip', ('size', 'verify'))
    def test_kullanicinin_hedefi_olcum_yerine_gecmez(
            self, kip, sivi_size, sivi_verify):
        """Kusurun kendisi: girdi 2,5 -> çizim 2,5. Bir daha olmamalı."""
        motor = sivi_size if kip == 'size' else sivi_verify
        blok = motor['structural_analysis']['chamber_structure']
        cizim = _cizim_kamarasi(motor)

        assert blok['safety_factor'] == pytest.approx(SF_HEDEFI, rel=0, abs=0)
        assert 'user input' in blok['safety_factor_source'].lower(), (
            'hedefin künyesi kayboldu; ihraç katmanı onu ölçüm sanabilir')
        # Hedef ÇİZİMDE de ayrı alanda ve DEĞİŞMEDEN durur.
        assert cizim['design_safety_factor_target'] == pytest.approx(
            SF_HEDEFI, rel=0, abs=0)
        # Çizilen cidarın katsayısı hedefin geri okunması OLAMAZ.
        assert cizim['safety_factor_at_drawn_wall'] != pytest.approx(
            SF_HEDEFI, rel=1e-9), (
            f'{kip}: çizim kullanıcının SF hedefini ölçüm gibi basıyor')

    @pytest.mark.parametrize('kip,beklenen_mm', (('size', 2.0),
                                                 ('verify', 5.0)))
    def test_cizilen_kalinlik_gerilmelerin_ait_oldugu_cidar(
            self, kip, beklenen_mm, sivi_size, sivi_verify):
        """Çizilen kalınlık ile SF'nin ait olduğu kalınlık aynı parça."""
        motor = sivi_size if kip == 'size' else sivi_verify
        blok = motor['structural_analysis']['chamber_structure']
        cizim = _cizim_kamarasi(motor)
        assert blok['wall_thickness'] == pytest.approx(beklenen_mm, rel=0,
                                                       abs=0)
        assert cizim['wall_thickness'] == pytest.approx(beklenen_mm, rel=0,
                                                        abs=0)
        assert cizim['wall_thickness_as_designed'] == pytest.approx(
            beklenen_mm, rel=0, abs=0)
        # Yapısal öneri AYRI alanda durur (2,0 mm imalat tabanı).
        assert cizim['wall_thickness_recommended'] == pytest.approx(
            blok['required_wall_thickness'], rel=1e-12)

    @pytest.mark.parametrize('kip', ('size', 'verify'))
    def test_kazanilmayan_dogrulama_iddiasi_basilmaz(
            self, kip, sivi_size, sivi_verify):
        """Fail-closed: sıvı bloğu ölçüm BEYAN etmediği sürece damga yok."""
        motor = sivi_size if kip == 'size' else sivi_verify
        cizim = _cizim_kamarasi(motor)
        if cizim['safety_factor_is_measured'] is True:
            # Ölçüm beyanı kazanıldıysa damga basılır (bekçi bu yolu da
            # kabul eder; ihraç ``measured_keys`` reçetesi OH-Z4-01'de).
            assert cizim['wall_verified_against_pressure_load'] is True
            assert VERIFIED_CLAIM in cizim['wall_thickness_source']
        else:
            assert cizim['wall_verified_against_pressure_load'] is False
            assert VERIFIED_CLAIM not in cizim['wall_thickness_source'], (
                f'{kip}: kazanılmamış doğrulama damgası çizime iniyor')
            # Sayı GİZLENMEZ ama NEDEN doğrulama olmadığı yazar.
            temel = (cizim['safety_factor_basis'] or '').lower()
            assert temel, f'{kip}: iddia yok, gerekçe de yok'
            assert any(im in temel for im in (
                'not a measurement', 'not a verification', 'read back',
                'design_safety_factor_target')), (
                f'{kip}: künye, basılan sayının neden bir doğrulama '
                f'olmadığını söylemiyor: {cizim["safety_factor_basis"]!r}')

    def test_beyansiz_blokta_alan_bos_birakilir(self, sivi_size):
        """Çözücü hiçbir şey beyan etmiyorsa ihraç SAYI UYDURMAZ."""
        from hrma.export.cad_visualization import NOT_AVAILABLE_SPEC
        import copy
        motor = copy.deepcopy(sivi_size)
        blok = motor['structural_analysis']['chamber_structure']
        for anahtar in ('design_mode', 'safety_factor_is_tautological',
                        'hoop_safety_factor', 'safety_factor',
                        'safety_factor_total'):
            blok.pop(anahtar, None)
        cizim = _cizim_kamarasi(motor)
        assert cizim['safety_factor_is_measured'] is None
        assert cizim['safety_factor_at_drawn_wall'] == NOT_AVAILABLE_SPEC
        assert cizim['wall_verified_against_pressure_load'] is False


# ---------------------------------------------------------------------------
# P9B2-07 / P9B2-25 — DXF DAMGASI ve ÖNERİ SATIRI (künye METNİ)
# ---------------------------------------------------------------------------
#
# Sentetik girdi bilerek kullanılır: bu iki kalem ihraç katmanının KENDİ
# davranışını sorar (hangi künye hangi bayrakta basılıyor), çözücünün
# doğruluğunu değil. Sayılar defterin ölçtüğü vakaların ta kendisidir.

#: Defterdeki iki kritik vaka: 1'in ALTINDA kalan iki emniyet katsayısı.
SF_KRITIK_VAKALAR = (0.8463, 0.103)

#: Yapısal analizin önerdiği, ama çizime inmeyen kalınlık [mm].
ONERILEN_MM = 23.18

#: Çizilen (as-designed) kalınlık [mm].
CIZILEN_MM = 5.0


def _kasa_motoru(**case_over):
    """Katı motorun ihraç katmanına verdiği gövdenin sadeleştirilmişi."""
    case = {
        'wall_thickness_mm': CIZILEN_MM,
        'recommended_wall_thickness_mm': ONERILEN_MM,
        'safety_factor': SF_KRITIK_VAKALAR[0],
        'design_safety_factor': 2.0,
        'design_mode': 'size',
        'safety_factor_is_tautological': True,
    }
    case.update(case_over)
    return {
        'motor_name': 'Z5GUARD-B1', 'motor_type': 'solid',
        'chamber_diameter': 0.100, 'chamber_length': 0.300,
        'throat_diameter': 0.030, 'exit_diameter': 0.060,
        'expansion_ratio': 4.0,
        'structural_analysis': {'case_analysis': case},
    }


def _dxf_metinleri(motor):
    """Üretilen DXF dosyasındaki TEXT varlıklarının metinleri."""
    ezdxf = pytest.importorskip('ezdxf')
    yol = os.path.join(tempfile.mkdtemp(prefix='z5guard-dxf-'), 'x.dxf')
    from hrma.export.drawing_generator import generate_dxf
    _silent(generate_dxf, motor, yol)
    doc = ezdxf.readfile(yol)
    return [e.dxf.text for e in doc.modelspace() if e.dxftype() == 'TEXT']


def _pdf_olcu_satirlari(motor):
    """PDF ölçü tablosunun satırları (etiket -> metin)."""
    from hrma.export.drawing_generator import _prepare, _schedule_rows
    md, dims = _prepare(motor)
    return dict(_schedule_rows(md, dims))


def _satir(metinler, onek):
    esler = [t for t in metinler if t.upper().startswith(onek)]
    assert len(esler) == 1, (
        f'{onek!r} ile başlayan satır sayısı {len(esler)} (beklenen 1): '
        f'{esler}')
    return esler[0]


class TestDXFDamgasiKazanilir:
    """P9B2-07 / P9B2-25: imalat dosyasındaki künye METNİ."""

    @pytest.mark.parametrize('sf', SF_KRITIK_VAKALAR)
    def test_boyutlandirilan_cidarda_dogrulama_damgasi_yok(self, sf):
        metinler = _dxf_metinleri(_kasa_motoru(safety_factor=sf))
        cidar = _satir(metinler, 'WALL THICKNESS')
        assert VERIFIED_CLAIM not in cidar, (
            f'SF {sf} olan boyutlandırılmış kasa DXF\'e doğrulama damgasıyla '
            f'iniyor: {cidar}')
        assert 'NOT a pressure-load verification' in cidar
        assert f'{CIZILEN_MM:.2f} mm' in cidar

    @pytest.mark.parametrize('sf', SF_KRITIK_VAKALAR)
    def test_oneri_satiri_dxfe_basiliyor(self, sf):
        """"önerilen 23,18 mm" hiçbir çıktıya basılmıyordu — artık basılıyor."""
        metinler = _dxf_metinleri(_kasa_motoru(safety_factor=sf))
        oneri = _satir(metinler, 'STRUCTURAL SIZING RECOMMENDS')
        assert f'{ONERILEN_MM:.2f} mm' in oneri
        assert 'DRAWN WALL IS NOT THE RECOMMENDED ONE' in oneri, (
            'çizilen ile önerilen farklı ama fark DXF\'te söylenmiyor')

    @pytest.mark.parametrize('sf', SF_KRITIK_VAKALAR)
    def test_birin_altindaki_katsayi_gizlenmez_ve_uyarilir(self, sf):
        metinler = _dxf_metinleri(_kasa_motoru(safety_factor=sf))
        satir = _satir(metinler, 'SAFETY FACTOR AT THE DRAWN WALL')
        assert f'{sf:.4f}' in satir, (
            f'1\'in altındaki katsayı ({sf}) DXF\'te dört haneyle yazmıyor: '
            f'{satir}')
        assert 'BELOW 1.0 - THE DRAWN WALL FAILS AT THIS PRESSURE' in satir
        assert 'NOT A VERIFICATION' in satir

    def test_gercek_dogrulamada_damga_susturulmaz(self):
        """Künye yalnız KAZANILDIĞINDA basılır — ama o zaman da basılır."""
        metinler = _dxf_metinleri(_kasa_motoru(
            design_mode='verify', safety_factor_is_tautological=False,
            safety_factor=1.83))
        cidar = _satir(metinler, 'WALL THICKNESS')
        assert VERIFIED_CLAIM in cidar
        satir = _satir(metinler, 'SAFETY FACTOR AT THE DRAWN WALL')
        assert '1.8300' in satir
        assert 'NOT A VERIFICATION' not in satir
        assert 'BELOW 1.0' not in satir

    def test_beyansiz_blokta_dxf_sayi_uydurmaz(self):
        metinler = _dxf_metinleri(_kasa_motoru(
            design_mode=None, safety_factor_is_tautological=None))
        cidar = _satir(metinler, 'WALL THICKNESS')
        assert VERIFIED_CLAIM not in cidar
        assert 'does not state whether the wall was checked' in cidar
        satir = _satir(metinler, 'SAFETY FACTOR AT THE DRAWN WALL')
        assert 'NOT PUBLISHED BY THIS ANALYSIS' in satir
        temel = _satir(metinler, 'SAFETY FACTOR BASIS')
        assert 'design_safety_factor_target' in temel

    @pytest.mark.parametrize('sf', SF_KRITIK_VAKALAR)
    def test_pdf_olcu_tablosu_dxf_ile_ayni_hukmu_veriyor(self, sf):
        """İki ürün yüzü aynı motoru anlatmalı (çapraz kanal ölçümü)."""
        motor = _kasa_motoru(safety_factor=sf)
        satirlar = _pdf_olcu_satirlari(motor)
        cidar = satirlar['Chamber wall thickness']
        assert VERIFIED_CLAIM not in cidar
        assert 'NOT a pressure-load verification' in cidar
        assert satirlar['Structural sizing recommends'] == (
            f'{ONERILEN_MM:.2f} mm')
        sf_satiri = satirlar['Safety factor at the drawn wall']
        assert f'{sf:.2f}' in sf_satiri
        assert 'BELOW 1.0 - THE DRAWN WALL FAILS' in sf_satiri
        assert '(NOT a verification)' in sf_satiri
        assert 'NOT a safety factor measured on the drawn wall' in (
            satirlar['Wall thickness note'])


# ---------------------------------------------------------------------------
# Veri katmanı: ağdan ve kullanıcı önbelleğinden YALITILMIŞ ortam
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def yalitilmis_veri():
    """Kullanıcı önbelleğini boş bir dizine bağlar, süreç içi cache'i siler.

    Kullanıcının makinesindeki ``propellant_cache.json`` teste sızarsa bekçi
    depoyu değil o makineyi ölçer (ölçüldü: yerel önbellekte
    ``polyethylene`` için ALTIN kaydı duruyordu). Bu fixture ile okunan tek
    kalıcı katman PAKETLE GELEN anlık görüntüdür.
    """
    mp = pytest.MonkeyPatch()
    gecici = tempfile.mkdtemp(prefix='z5guard-veri-')
    mp.setenv('HRMA_USER_DATA_DIR', gecici)
    from hrma.data.open_source_propellant_api import propellant_api
    eski = dict(propellant_api.cache)
    propellant_api.cache.clear()
    yield gecici
    propellant_api.cache.clear()
    propellant_api.cache.update(eski)
    mp.undo()


# ---------------------------------------------------------------------------
# P9B5-05 — CID ⟷ MADDE: deny-list + kimlik
# ---------------------------------------------------------------------------

#: Ölçülen YANLIŞ MADDE kayıtları (Z1, PubChem PUG-REST ile doğrulandı).
#: Bu CID'ler ``known_cids`` haritasında bir daha ASLA görünmemeli.
ZEHIRLI_CIDLER = {
    53298156: 'htpb -> C21H17ClN4O, kinaz inhibitörü İLAÇ molekülü',
    23985: 'polyethylene -> Au, ALTIN (rho 19 300 kg/m3)',
    6658: 'pmma -> C5H8O2, metil metakrilat MONOMERİ (rho 936 vs 1180)',
    6037: 'mmh -> metotreksat (2026-07-16 düzeltmesi)',
}

#: Paketli anlık görüntüdeki her ``pubchem:<ad>`` kaydının GERÇEKTEN
#: taşıması gereken formül. Kaynak: PubChem PUG-REST kimlik sorgusu
#: (docs/arastirma/fizik/Z1-yogunluk-dogrulama.md §9.2e-g).
BEKLENEN_FORMULLER = {
    'ethanol': 'C2H6O',
    'h2o2': 'H2O2',
    'lh2': 'H2',
    'lox': 'O2',
    'methane': 'CH4',
    'mmh': 'CH6N2',
    'n2o': 'N2O',
    'n2o4': 'N2O4',
    'paraffin': 'C28H58',
    'rp1': 'C16H34',
    'udmh': 'C2H8N2',
}


def _api():
    from hrma.data.open_source_propellant_api import OpenSourcePropellantAPI
    return OpenSourcePropellantAPI()


def _anlik_goruntu_pubchem():
    from hrma.data import offline_store
    with open(offline_store.SNAPSHOT_PATH, encoding='utf-8') as fh:
        veri = json.load(fh)
    return {k.split(':', 1)[1]: v['data']
            for k, v in veri.get('entries', {}).items()
            if k.startswith('pubchem:')}


class TestPubChemKimlikKapisi:
    """P9B5-05: hangi CID hangi maddeye ait — deny-list + kimlik."""

    def test_zehirli_cidler_haritada_yok(self):
        harita = _api().known_cids
        bulunan = {cid: ad for ad, cid in harita.items()
                   if cid in ZEHIRLI_CIDLER}
        assert not bulunan, (
            'ölçülen yanlış-madde CID\'leri known_cids\'e geri döndü: '
            + '; '.join(f'{ad}={cid} ({ZEHIRLI_CIDLER[cid]})'
                        for cid, ad in bulunan.items()))

    def test_polimerler_gomulu_cid_tasimaz(self):
        api = _api()
        sizanlar = sorted(set(api.PUBCHEM_POLYMER_DENY) & set(api.known_cids))
        assert not sizanlar, (
            f'deny-list\'teki polimerler known_cids\'te de duruyor: '
            f'{sizanlar} — iki kural çelişirse hangisinin kazanacağı '
            f'çağrı sırasına kalır')

    def test_deny_listesi_kimlik_yolunu_kapatiyor(self, yalitilmis_veri):
        """Ad araması da gömülü CID de kapalı: fail-closed."""
        api = _api()
        assert api.PUBCHEM_POLYMER_DENY, 'deny-list boşaltılmış'
        for ad in api.PUBCHEM_POLYMER_DENY:
            assert _silent(api.get_compound_cid, ad) is None, (
                f'{ad}: polimer için PubChem kimlik yolu açık — ad araması '
                f'tekrarlanabilir biçimde BAŞKA MADDE getiriyor')
        # Büyük harf / tire / boşluk varyantları da aynı kapıdan geçer.
        for varyant in ('HTPB', 'Poly-Ethylene', 'poly ethylene'):
            assert _silent(api.get_compound_cid, varyant) is None, (
                f'{varyant!r} deny-list normalizasyonunu atlatıyor')

    def test_polimer_olmayanlarin_kimligi_kapanmadi(self, yalitilmis_veri):
        """Kapı yalnız TEKİL BİLEŞİK OLMAYANLARA ait; gerçek moleküller açık.

        ÇEVRİLDİ (ÖH D15 birleşme etkileşimi, 1 Eylül 2026). Bu liste eskiden
        ``('rp1', 11006)`` çiftini de taşıyordu: Z1 (2026-08-27) hekzadekan
        CID'ini "kimlik/formül vekili doğru, yalnız yoğunluk vekili yanlış"
        diye SAKLAMIŞTI. D15 / defter P9B4-05 aynı adı
        ``PUBCHEM_POLYMER_DENY``ye ekledi ve iki kural çelişti.

        Çelişki gevşetilerek değil ÖLÇÜLEREK çözüldü — Z1'in gerekçesi
        deponun kendi tablolarıyla çürüyor:

          CID 11006 = hekzadekan C16H34, MA 226,44
          hrma/data/chemical_database.py:145   RP1  C12H23, MA 167,31 -> +%35,3
          hrma/data/propellant_database.py:204              MA 170,33 -> +%32,9

        Molekül ağırlığı bir KİMLİK büyüklüğüdür; "vekil yalnız yoğunlukta
        yanlış" savunması bu sayıyla ayakta kalmıyor. RP-1 bir kerosen
        kesitidir (karışım), tekil bileşik kaydı onun kimliği olamaz.
        İddianın kendisi (kapı yalnız kapsamına girene ait) korunuyor: tekil
        bileşikler AYNEN açık kalmalı.
        """
        api = _api()
        for ad, beklenen in (('n2o', 948), ('lox', 977),
                             ('mmh', 6061), ('udmh', 5976)):
            assert _silent(api.get_compound_cid, ad) == beklenen
        # Karışımlar kapının İÇİNDE: tek kural (deny), gömülü ikinci CID yok.
        for karisim in ('rp1', 'kerosene', 'paraffin'):
            assert karisim in api.PUBCHEM_POLYMER_DENY, (
                f'{karisim} karışımı deny-list\'ten düşmüş')
            assert _silent(api.get_compound_cid, karisim) is None, (
                f'{karisim}: karışıma tekil bileşik kimliği basılıyor')
            assert karisim not in api.known_cids, (
                f'{karisim}: gömülü CID geri geldi — iki kural yine çelişir')

    @pytest.mark.parametrize('ad,formul', sorted(BEKLENEN_FORMULLER.items()))
    def test_anlik_goruntu_kaydi_dogru_maddeyi_tasiyor(self, ad, formul):
        kayitlar = _anlik_goruntu_pubchem()
        if ad in _api().PUBCHEM_POLYMER_DENY:
            # ÇEVRİLDİ (ÖH D15, 1 Eylül 2026): eskiden burada `pytest.skip`
            # vardı. D15 / P9B4-05 `rp1` ve `paraffin`i deny-list'e alıp
            # kayıtlarını anlık görüntüden silince atlama KALICI hale geldi
            # ve bekçi sessizce körelmişti. Kapıya girmiş bir ad için doğru
            # iddia "kaydı yok" DEĞİL, "kaydı OLMAMALI"dır.
            assert ad not in kayitlar, (
                f'{ad} deny-list\'te ama paketli anlık görüntüde hâlâ '
                f'CID {kayitlar[ad].get("cid")} / '
                f'{kayitlar[ad].get("formula")} kaydı duruyor')
            return
        if ad not in kayitlar:
            pytest.skip(f'paketli anlık görüntüde {ad} kaydı yok')
        assert kayitlar[ad]['formula'] == formul, (
            f'{ad}: paketli anlık görüntü {kayitlar[ad]["formula"]!r} '
            f'formülünü taşıyor, beklenen {formul!r} — CID '
            f'{kayitlar[ad].get("cid")} başka bir maddeye ait')

    def test_polimerlerin_anlik_goruntu_kaydi_kalmadi(self, yalitilmis_veri):
        """BORÇ ÖDENDİ — im kaldırıldı (ÖH D15, 1 Eylül 2026).

        Bu test ``xfail(strict=True)`` ile imliydi: deny-list yalnız
        ``get_compound_cid`` yolunu kapatıyor, ``get_pubchem_properties``
        çevrimdışı depoyu ÖNCE okuduğu için paketli anlık görüntüdeki polimer
        kayıtları kapıyı ATLIYORDU (ölçüm, 27 Ağustos 2026: htpb -> CID
        53298156 / C21H17ClN4O kinaz inhibitörü ilaç; pmma -> CID 6658 /
        C5H8O2 monomer; abs -> CID 24756).

        ÖH D15 / defter P9B4-05 kapıyı depo okumasına da uyguladı ve beş
        yanlış kimlik kaydını anlık görüntüden SİLDİ; bu bekçi XPASS verdi.
        İddia aynen duruyor, yalnız borç imi kalktı — kayıt geri gelirse
        test KIRMIZI verir.
        """
        api = _api()
        kayitlar = _anlik_goruntu_pubchem()
        sizanlar = sorted(set(api.PUBCHEM_POLYMER_DENY) & set(kayitlar))
        assert not sizanlar, (
            'deny-list\'teki polimerler paketli anlık görüntüde duruyor ve '
            'get_pubchem_properties oradan yabancı madde döndürüyor: '
            + '; '.join(f'{ad}=CID {kayitlar[ad].get("cid")} '
                        f'({kayitlar[ad].get("formula")})'
                        for ad in sizanlar))

    def test_urun_yuzunde_yabanci_molekul_kimligi_yok(self, app_client,
                                                      yalitilmis_veri):
        """BORÇ ÖDENDİ — im kaldırıldı (ÖH D15, 1 Eylül 2026).

        İm şunu söylüyordu: ``/api/get-propellant-properties`` hybrid_fuel/htpb
        yanıtı YOĞUNLUĞU merkezî tablodan alıyor (920 — Z1 onarımı tuttu) ama
        KİMLİĞİ hâlâ ilaç molekülünden basıyordu (ölçüm:
        formula='C21H17ClN4O', molecular_weight='376.8',
        name='N-(3-chloro-4-methoxyphenyl)-4-(pyridin-3-ylmethyl)phthalazin-
        1-amine'). D15 / P9B4-05 anlık görüntüyü temizleyince ürün yüzü de
        temizlendi ve bekçi XPASS verdi.
        """
        yanit = _silent(app_client.post, '/api/get-propellant-properties',
                        json={'propellant_type': 'hybrid_fuel',
                              'propellant_name': 'htpb'},
                        headers={'Host': '127.0.0.1:8080'})
        assert yanit.status_code == 200
        ozellikler = yanit.get_json().get('properties', {})
        assert 'phthalazin' not in str(ozellikler.get('name', '')).lower(), (
            f'HTPB kaydı bir ilaç molekülünün adını taşıyor: '
            f'{ozellikler.get("name")!r}')
        assert 'Cl' not in str(ozellikler.get('formula', '')), (
            f'HTPB formülü klor içeriyor: {ozellikler.get("formula")!r}')

    def test_htpb_yogunlugu_merkezi_tablodan_geliyor(self, app_client,
                                                     yalitilmis_veri):
        """Z1'in TUTAN ayağı: sayı yabancı molekülden gelmiyor (regresyon)."""
        yanit = _silent(app_client.post, '/api/get-propellant-properties',
                        json={'propellant_type': 'hybrid_fuel',
                              'propellant_name': 'htpb'},
                        headers={'Host': '127.0.0.1:8080'})
        ozellikler = yanit.get_json().get('properties', {})
        assert ozellikler['density'] == pytest.approx(920, rel=0, abs=0)
        # Kategori yedeği olduğu KANITLANAN alanlar yayından düşmüş olmalı.
        assert 'density' in ozellikler.get('category_defaults_suppressed', [])


# ---------------------------------------------------------------------------
# P9B4-04 — kriyojen depolama-durumu kapısı (872x vakası)
# ---------------------------------------------------------------------------

#: ÖLÇÜLDÜ (27 Ağustos 2026, CoolProp): depolama durumu ⟷ 298,15 K / 1 atm.
#: Oran, kalemin başlığındaki 872x'in ta kendisidir.
KRIYOJEN_VAKALARI = {
    # ad: (depolama yoğunluğu, depolama T [K], en az beklenen oran)
    'lox': (1141.1612390428575, 90.19, 800.0),
    'lh2': (70.94949797943943, 20.28, 800.0),
    'methane': (422.35169427836865, 111.67, 600.0),
    # N₂O kendinden basınçlı: 293,15 K'de doymuş SIVI.
    'n2o': (785.1039703874175, 293.15, 400.0),
}


class TestKriyojenDepolamaDurumuKapisi:
    """P9B4-04: tek tüketici 298,15 K varsayımıyla kapıyı kapatamaz."""

    @pytest.mark.parametrize('ad', sorted(KRIYOJEN_VAKALARI))
    def test_872x_vakasi_depolama_durumundan_okunuyor(self, ad,
                                                      yalitilmis_veri):
        from hrma.data.open_source_propellant_api import propellant_api
        beklenen, T_dep, en_az_oran = KRIYOJEN_VAKALARI[ad]

        depolama = _silent(propellant_api.get_coolprop_properties, ad)
        ortam = _silent(propellant_api.get_coolprop_properties, ad,
                        298.15, 101325)
        if 'density' not in depolama:
            _coolprop_yoksa_atla(depolama)

        assert depolama['state_temperature_K'] == pytest.approx(T_dep,
                                                                rel=1e-9)
        assert depolama['density'] == pytest.approx(beklenen, rel=1e-9), (
            f'{ad}: depolama durumu yoğunluğu kaydı {beklenen} idi')
        assert 'liquid' in str(depolama.get('phase', '')).lower()
        # Kusurun büyüklüğü: aynı akışkan 298,15 K'de GAZ.
        oran = depolama['density'] / ortam['density']
        assert oran > en_az_oran, (
            f'{ad}: depolama/ortam oranı {oran:.1f}x — kapı ölçüsünü '
            f'yitirdi (ölçülen taban {en_az_oran}x)')
        assert 'liquid' not in str(ortam.get('phase', '')).lower()

    @pytest.mark.parametrize('ad', sorted(KRIYOJEN_VAKALARI))
    def test_uc_gaz_fazi_sayisini_yayimlamiyor(self, ad, app_client,
                                               yalitilmis_veri):
        """Tek tüketici (uç) depolama durumunu okumalı, 298,15 K'yi değil."""
        from hrma.data.open_source_propellant_api import propellant_api
        beklenen, _T, _oran = KRIYOJEN_VAKALARI[ad]
        tur = 'oxidizer' if ad in ('lox', 'n2o') else 'liquid_fuel'
        yanit = _silent(app_client.post, '/api/get-propellant-properties',
                        json={'propellant_type': tur, 'propellant_name': ad},
                        headers={'Host': '127.0.0.1:8080'})
        assert yanit.status_code == 200
        ozellikler = yanit.get_json()['properties']

        depolama = _silent(propellant_api.get_coolprop_properties, ad)
        if 'density' not in depolama:
            _coolprop_yoksa_atla(depolama)
        ortam = _silent(propellant_api.get_coolprop_properties, ad,
                        298.15, 101325)

        assert ozellikler['density'] == pytest.approx(beklenen, rel=1e-9)
        assert ozellikler['density'] != pytest.approx(ortam['density'],
                                                      rel=1e-3), (
            f'{ad}: uç 298,15 K gaz yoğunluğunu yayımlıyor '
            f'({ortam["density"]!r})')
        # Sayının hangi hâle ait olduğu YANINDA durur (künye).
        durum = ozellikler.get('storage_state')
        assert isinstance(durum, dict) and durum, (
            f'{ad}: sayı var, hâl künyesi yok — okuyan hangi sıcaklığın '
            f'yoğunluğuna baktığını bilemez')
        assert durum['state_temperature_K'] == pytest.approx(
            depolama['state_temperature_K'], rel=1e-9)
        assert 'liquid' in str(durum.get('phase', '')).lower()


# ---------------------------------------------------------------------------
# P9B5-04 — "iki N2O yoğunluğu" tek, sıcaklık-parametreli kaynağa indi
# ---------------------------------------------------------------------------

class TestN2OTekKaynak:
    """P9B5-04 ölçüm ayağı. (Kanon SICAKLIK ETİKETİ kararı Berke'dedir.)"""

    def test_tek_kaynak_sicaklikla_parametreli(self):
        from hrma.data.external_data_fetcher import oxidizer_reference_density
        okumalar = {T: oxidizer_reference_density('n2o', T)
                    for T in (184.67, 293.15, 298.15)}
        for T, kayit in okumalar.items():
            assert kayit['state_applied'] is True
            assert kayit['reference_T_K'] == pytest.approx(T, rel=1e-12)
            assert f'{T:g}' in kayit['source'] or f'{T}' in kayit['source'], (
                f'{T} K okuması künyesinde sıcaklığını taşımıyor: '
                f'{kayit["source"]!r}')
        # Doymuş sıvı yoğunluğu sıcaklıkla MONOTON azalır: 1220 ⟷ 745 ⟷ 785
        # üçlüsü çelişki değil, aynı eğrinin üç noktası.
        yogunluklar = [okumalar[T]['density'] for T in (184.67, 293.15,
                                                        298.15)]
        assert yogunluklar[0] > yogunluklar[1] > yogunluklar[2], (
            f'aynı eğrinin üç noktası monoton değil: {yogunluklar}')

    def test_1220_yalniz_kaynama_noktasinda_yasiyor(self):
        """Eski kusur: 1220 (NKN değeri) 293 K'ye taşınıp yayımlanıyordu."""
        from hrma.data.external_data_fetcher import oxidizer_reference_density
        nkn = oxidizer_reference_density('n2o', 184.67)['density']
        oda = oxidizer_reference_density('n2o', 293.15)['density']
        assert nkn == pytest.approx(1230.487546826561, rel=1e-9)
        assert oda == pytest.approx(785.1039703874175, rel=1e-9)
        # Eski doğrusal ekstrapolasyonun 293,15 K'de ürettiği sayı (948,80)
        # bir daha yayımlanmamalı.
        eski_ekstrapolasyon = 1220.0 - 2.5 * (293.15 - 184.67)
        assert abs(oda - eski_ekstrapolasyon) > 100.0, (
            f'293,15 K okuması eski ekstrapolasyona ({eski_ekstrapolasyon:.2f}) '
            f'geri döndü')

    def test_745_ve_785_ayni_egrinin_iki_sicakligi(self):
        """İkilik BİTTİ: aynı T'de iki sayı %0,5'ten fazla ayrışmıyor."""
        from hrma.data.external_data_fetcher import oxidizer_reference_density
        from hrma.data.propellant_database import N2O_LIQUID_DENSITY_SAT_25C
        korelasyon_25C = oxidizer_reference_density('n2o', 298.15)['density']
        # Merkezî tablodaki 745,0 NIST WebBook'un 25 °C değeri; korelasyon
        # (CoolProp/REFPROP, Lemmon & Span 2006) 742,93 veriyor.
        sapma = abs(korelasyon_25C - N2O_LIQUID_DENSITY_SAT_25C) / \
            N2O_LIQUID_DENSITY_SAT_25C
        assert sapma < 0.005, (
            f'aynı sıcaklıkta iki N2O yoğunluğu %{sapma * 100:.2f} ayrışıyor: '
            f'sabit {N2O_LIQUID_DENSITY_SAT_25C} ⟷ korelasyon '
            f'{korelasyon_25C!r}')
        # 20 °C ⟷ 25 °C farkı GERÇEK bir fizik farkıdır, çelişki değil.
        korelasyon_20C = oxidizer_reference_density('n2o', 293.15)['density']
        assert korelasyon_20C > korelasyon_25C

    def test_sicaklik_verilmezse_varsayim_beyan_ediliyor(self):
        from hrma.data.external_data_fetcher import oxidizer_reference_density
        kayit = oxidizer_reference_density('n2o', None)
        assert kayit['reference_T_K'] == pytest.approx(298.15, rel=1e-12)
        assert kayit['note'] and '25 C' in kayit['note'], (
            'sıcaklık verilmediğinde varsayılan hâl SESSİZCE seçiliyor')


# ---------------------------------------------------------------------------
# P9B5-25 — jenerik yedek BEYAN EDİLİR
# ---------------------------------------------------------------------------

class TestJenerikYedekBeyani:
    """P9B5-25: 800 kg/m³ + 0,001 Pa·s dayatması artık künyeli."""

    def test_taninan_bilesikler_kendi_sayisini_aliyor(self):
        from hrma.data.web_propellant_api import WebPropellantAPI
        api = WebPropellantAPI()
        for ad, rho in (('lox', 1141.7), ('rp1', 815.0), ('lh2', 70.85),
                        ('methane', 422.6)):
            veri = _silent(api._get_fallback_data, ad, 'bekci')
            assert veri['density'] == pytest.approx(rho, rel=0, abs=0)
            assert veri.get('error') is None

    @pytest.mark.parametrize('ad', ('n2o4', 'h2o2', 'mmh', 'udmh',
                                    'hydrazine'))
    def test_tanınmayan_bilesikte_jenerik_ADIYLA_geliyor(self, ad):
        """Sayı susturulmuyor ama 'bilinmiyor' damgası SAYININ YANINDA."""
        from hrma.data.web_propellant_api import WebPropellantAPI
        veri = _silent(WebPropellantAPI()._get_fallback_data, ad, 'bekci')
        assert veri['density'] == 800 and veri['viscosity'] == 0.001
        assert veri['error'] == 'Unknown compound', (
            f'{ad}: jenerik 800/0,001 sessizce veriliyor — tüketici bunun '
            f'akışkana ait olmadığını göremez')
        assert veri['status'] == 'fallback'
        assert veri['data_state'] == 'offline'
        assert 'Fallback Data' in veri['source']

    def test_enjektor_viskozitesi_uc_kademeli_ve_kunyeli(self):
        """kullanıcı -> akışkan tablosu -> BEYANLI jenerik sıralaması."""
        from hrma.utils.injector_design import InjectorDesign
        ortak = dict(mdot_ox=2.0, chamber_pressure=20, tank_pressure=50)

        kullanici = _silent(InjectorDesign, oxidizer_type='n2o',
                            oxidizer_viscosity=0.00042, **ortak)
        assert kullanici.mu_ox == pytest.approx(0.00042, rel=0, abs=0)
        assert kullanici.viscosity_basis == 'user input'

        tablo = _silent(InjectorDesign, oxidizer_type='lox', **ortak)
        assert tablo.mu_ox == pytest.approx(0.00019, rel=1e-12)
        assert 'lox' in tablo.viscosity_basis
        assert 'generic' not in tablo.viscosity_basis.lower()

        jenerik = _silent(InjectorDesign, oxidizer_type='',
                          oxidizer_density=1000.0, **ortak)
        assert 'generic assumption' in jenerik.viscosity_basis
        assert 'unspecified' in jenerik.viscosity_basis
        assert 'NOT taken from another fluid' in jenerik.viscosity_basis, (
            'jenerik viskozite başka bir akışkanın değeri sanılabilir')

    def test_kunye_rapora_giriyor(self):
        """``viscosity_basis`` yalnız nesnede değil, RAPORDA da var."""
        from hrma.utils.injector_design import InjectorDesign
        tasarim = _silent(InjectorDesign, mdot_ox=2.0, chamber_pressure=20,
                          tank_pressure=50, oxidizer_type='',
                          oxidizer_density=1000.0)
        tasarim.set_showerhead_params()
        rapor = _silent(tasarim.calculate)
        assert isinstance(rapor, dict), f'rapor sözlük değil: {type(rapor)}'
        assert 'viscosity_basis' in rapor, (
            'viskozitenin dayanağı rapora hiç girmiyor; okuyan 2e-4\'ün '
            'nereden geldiğini göremez')
        assert 'generic assumption' in rapor['viscosity_basis']
        assert 'NOT taken from another fluid' in rapor['viscosity_basis']
        # Kardeş künye (yüzey gerilimi) aynı desende: sessiz ödünç yok.
        assert 'NOT taken from another fluid' in rapor['surface_tension_basis']


# ---------------------------------------------------------------------------
# P9B5-06 — ŞABLON EZME KAPISI (liquid.html)
# ---------------------------------------------------------------------------

#: Uçtan gelen sayının ezmeye YETKİLİ olmadığı, yalnız hâl çözümlü değerin
#: yazabileceği form alanları.
KORUNAN_ALANLAR = ('fuel_density', 'fuel_viscosity',
                   'oxidizer_density', 'oxidizer_viscosity')

#: ÖLÇÜLDÜ: hâl çözümlü DEĞİL (storage_state yok) -> forma YAZILMAZ.
#: Sayılar merkezî tablonun doğru değerleridir; kategori yedeği (800 / 1200)
#: uçta zaten düşürülmüştür — ikisi birden kilitlenir.
EZMEYEN_VAKALAR = {
    ('liquid_fuel', 'rp1'): 810,
    ('liquid_fuel', 'mmh'): 875,
    ('liquid_fuel', 'udmh'): 791,
    ('oxidizer', 'n2o4'): 1443,
}

#: ÖLÇÜLDÜ: hâl çözümlü -> forma YAZILIR.
EZEN_VAKALAR = {
    ('oxidizer', 'lox'): 1141.1612390428575,
    ('oxidizer', 'n2o'): 785.1039703874175,
    ('liquid_fuel', 'lh2'): 70.94949797943943,
    ('liquid_fuel', 'methane'): 422.35169427836865,
}


def _liquid_html():
    from hrma import app as app_modulu
    yol = os.path.join(os.path.dirname(os.path.abspath(app_modulu.__file__)),
                       'templates', 'liquid.html')
    with open(yol, encoding='utf-8') as fh:
        return fh.read()


def _fonksiyon_araligi(metin, ad):
    """``<ad>`` JS fonksiyonunun gövdesinin (başlangıç, bitiş) ofseti.

    Bitiş, AYNI girintideki bir sonraki fonksiyon bildirimidir; şablon
    tutarlı biçimde 8 boşlukla girintili yazıldığı için bu ayraç güvenilir
    ve dosya değişince sessizce kaymaz (bulunamazsa test kırılır).
    """
    bas = metin.find(f'function {ad}(')
    assert bas != -1, f'{ad} fonksiyonu şablonda yok'
    sonraki = re.search(r'\n        (?:async )?function ', metin[bas + 10:])
    assert sonraki is not None, f'{ad} fonksiyonunun bitişi bulunamadı'
    return bas, bas + 10 + sonraki.start()


def _yazma_ofsetleri(metin, alan):
    """Alana SAYI yazan her deyimin ofseti.

    ÖH D31 · arayuz-panel a3 (14 Eyl 2026) — DESEN GÜNCELLENDİ (testin
    kendi uyarısı: "bekçi kör kaldı, desen güncellenmeli").

    Şablon artık uçtan gelen değeri ``liquidAutofillField('<alan>', ...)``
    sarmalayıcısıyla yazıyor (OH-Z1-05: makine dolumu bayraklanır ki
    çözüm gelmediğinde BAYAT sayı temizlenebilsin, kullanıcının ELLE
    yazdığı sayıya ise dokunulmasın). Sarmalayıcı sayılmazsa bekçi
    "hiç yazma yok" der ve kapıyı DENETLEMEZ — sahte yeşil.

    ``liquidClearUnresolvedField`` bilerek SAYILMAZ: o alanı BOŞALTIR,
    yani kapının koruduğu tehlikenin (denetlenmemiş SAYININ alana
    yazılması) tam tersidir; fail-closed tarafta durur.
    """
    desenler = (
        re.compile(
            r"getElementById\(\s*['\"]" + re.escape(alan)
            + r"['\"]\s*\)\s*(?:\.value\s*=|\n\s*\.value\s*=)"),
        re.compile(r"liquidAutofillField\(\s*['\"]" + re.escape(alan)
                   + r"['\"]\s*,"),
    )
    ofsetler = []
    for desen in desenler:
        ofsetler.extend(e.start() for e in desen.finditer(metin))
    return sorted(ofsetler)


def _kapsayan_blok_basligi(metin, ofset):
    """``ofset``teki deyimi KAPSAYAN bloğun başlığı (``if (...)`` metni).

    Pencere taraması YETMEZ: ölçüldü (bu bekçinin M8 mutasyon denemesi,
    27 Ağustos 2026) — kapı ``if``ten sökülünce bile hemen üstteki
    ``markFieldProvenance(..., prov.stateResolved)`` satırı 400 karakterlik
    pencerede duruyor ve gevşek bir bekçi mutasyonu KAÇIRIYOR. Bu yüzden
    kapsayan blok GERÇEKTEN çözülür: ofsetten geriye doğru süslü parantez
    derinliği sayılır, dengesiz kalan ilk ``{`` kapsayan bloğun açılışıdır;
    başlık, ondan önceki deyim sonuna (``;`` / ``{`` / ``}``) kadar okunur.
    """
    derinlik = 0
    i = ofset - 1
    while i >= 0:
        ch = metin[i]
        if ch == '}':
            derinlik += 1
        elif ch == '{':
            if derinlik == 0:
                break
            derinlik -= 1
        i -= 1
    assert i >= 0, f'{ofset}: kapsayan blok açılışı bulunamadı'
    j = i - 1
    while j >= 0 and metin[j] not in ';{}':
        j -= 1
    return metin[j + 1:i]


class TestSablonEzmeKapisi:
    """P9B5-06: form alanı yalnız HÂL ÇÖZÜMLÜ sayıyla güncellenir."""

    def test_kapi_fonksiyonu_hal_cozumunu_olcuyor(self):
        metin = _liquid_html()
        assert 'function propellantProvenance(' in metin, (
            'ezme kapısının karar fonksiyonu şablondan kaldırılmış')
        # Kapının ayırt edici sinyali: storage_state + sayısal density.
        assert re.search(
            r"stateResolved\s*=\s*!!\(\s*state\s*&&\s*typeof\s+props\.density"
            r"\s*===\s*['\"]number['\"]\s*\)", metin), (
            'hâl çözümü ölçütü değişmiş; kapı artık storage_state\'e '
            'bakmıyor olabilir')

    @pytest.mark.parametrize('alan', KORUNAN_ALANLAR)
    def test_uc_yolundaki_her_yazma_kapinin_arkasinda(self, alan):
        """Uçtan gelen sayı, ancak kapı açıksa alana yazılır."""
        metin = _liquid_html()
        bas, son = _fonksiyon_araligi(metin, 'loadPropellantProperties')
        icerideki = [o for o in _yazma_ofsetleri(metin, alan)
                     if bas <= o < son]
        assert icerideki, (
            f'{alan}: uç yolunda hiç yazma bulunamadı — bekçi kör kaldı, '
            f'desen güncellenmeli')
        for ofset in icerideki:
            baslik = _kapsayan_blok_basligi(metin, ofset)
            assert baslik.lstrip().startswith('if'), (
                f'{alan} alanına koşulsuz yazma var (ofset {ofset}): '
                f'kapsayan blok bir "if" değil -> {baslik.strip()[:120]!r}')
            assert 'prov.stateResolved' in baslik, (
                f'{alan} alanına KAPISIZ yazma var (ofset {ofset}): '
                f'kategori yedeği kullanıcının alanını ezebilir. Kapsayan '
                f'koşul: {baslik.strip()[:160]!r}')

    @pytest.mark.parametrize('alan', KORUNAN_ALANLAR)
    def test_kapi_disinda_yalniz_kullanici_baslattigi_yazma_var(self, alan):
        """Uç yolunun DIŞINDA kalan tek yazma ``resetForm`` olmalı.

        Kapı, yalnız ``loadPropellantProperties`` içine konursa yeni bir
        API kolu kapının yanından dolaşabilir. Bu bekçi, korunan alanlara
        yazan HER yerin ya kapı arkasında ya da kullanıcının bastığı
        "sıfırla" düğmesinde olduğunu ölçer.
        """
        metin = _liquid_html()
        uc = _fonksiyon_araligi(metin, 'loadPropellantProperties')
        reset = _fonksiyon_araligi(metin, 'resetForm')
        kacaklar = [o for o in _yazma_ofsetleri(metin, alan)
                    if not (uc[0] <= o < uc[1] or reset[0] <= o < reset[1])]
        assert not kacaklar, (
            f'{alan}: ne ezme kapısında ne de resetForm\'da olan yazma(lar) '
            f'var (ofset {kacaklar}) — kapının yanından dolaşan bir kol '
            f'doğmuş olabilir')

    @pytest.mark.parametrize('alan', KORUNAN_ALANLAR)
    def test_kaynak_alan_renkle_isaretleniyor(self, alan):
        metin = _liquid_html()
        assert f"markFieldProvenance('{alan}'" in metin, (
            f'{alan}: alanın çözülmüş mü yedek mi olduğu ekranda '
            f'görünmüyor')

    @pytest.mark.parametrize('anahtar', sorted(EZMEYEN_VAKALAR))
    def test_kategori_yedegi_hal_cozumu_TASIMIYOR(self, anahtar, app_client,
                                                  yalitilmis_veri):
        """Kapının girdisi: bu akışkanlarda ``storage_state`` YOK."""
        tur, ad = anahtar
        yanit = _silent(app_client.post, '/api/get-propellant-properties',
                        json={'propellant_type': tur, 'propellant_name': ad},
                        headers={'Host': '127.0.0.1:8080'})
        ozellikler = yanit.get_json()['properties']
        assert not ozellikler.get('storage_state'), (
            f'{ad}: hâl künyesi yokken var gibi görünüyor — kapı açılır ve '
            f'çözülmemiş sayı forma iner')
        # Kategori yedeği (rp1/mmh/udmh 800, n2o4 1200) uçta ÖLDÜ:
        # yayımlanan sayı merkezî tablonun kendi değeri.
        assert ozellikler['density'] == pytest.approx(
            EZMEYEN_VAKALAR[anahtar], rel=0, abs=0), (
            f'{ad}: yoğunluk {ozellikler["density"]!r} — kategori yedeği '
            f'merkezî tabloyu yeniden eziyor olabilir')

    @pytest.mark.parametrize('anahtar', sorted(EZEN_VAKALAR))
    def test_hal_cozumlu_deger_kapidan_geciyor(self, anahtar, app_client,
                                               yalitilmis_veri):
        """Kapı bir SUSTURUCU değil: gerçek hâl çözümü forma inmeli."""
        tur, ad = anahtar
        yanit = _silent(app_client.post, '/api/get-propellant-properties',
                        json={'propellant_type': tur, 'propellant_name': ad},
                        headers={'Host': '127.0.0.1:8080'})
        ozellikler = yanit.get_json()['properties']
        if not ozellikler.get('storage_state'):
            _coolprop_yoksa_atla(ozellikler)
        assert isinstance(ozellikler['density'], float)
        assert ozellikler['density'] == pytest.approx(EZEN_VAKALAR[anahtar],
                                                      rel=1e-9)
