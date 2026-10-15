"""ÖH D35 · onemli-kati-cad (a1) — üç ÖNEMLİ kalemin davranış bekçileri.

Kalemler ve ölçümleri
---------------------
**OH-ON-03** — katı örnek proje yüklenip yeniden hesaplanınca %10,5 kayıyordu.
``docs/scofield/raw/OH/D35/onemli-kati-cad/a1/10_once.json`` (A bölümü):
``.hrma`` dosyası verim alanlarını taşımadığı için form kendi ``value=``
varsayılanlarını gönderiyor, aynı proje iki farklı sayı üretiyordu::

    yaprak            API yolu (.hrma)   FORM yolu (kullanıcı)   fark
    isp_sea_level        140,109 s          125,401 s          -%10,4974
    total_impulse       3306,767 N·s       2959,642 N·s        -%10,4974
    c_star               915,900 m/s        870,105 m/s         -%5,0000

**OH-ON-04** — STEP'teki yakıt tanesi 3 BATES segmenti değil TEK parça boruydu.
(C bölümü, FreeCAD 7.9): ``fuel_grain.step`` 1 katı, 4 yüzey, x 36,4 -> 396,4
kesintisiz. Analiz ise ``number_of_segments = 3`` yayımlıyor ve nötr Kn
eğrisini (145,6 -> 148,4) ALTI uç cepheden kuruyor. O STEP'ten imal edilen
tane, analiz edilen motorun tanesi değildi.

**OH-ON-05** — çözücü cidarı kendisi boyutlandırdığı hâlde makine-okur beyan
yoktu. (B bölümü): ``case_thickness`` boşken ``defaults_applied`` yalnız
``propellant_type``ı anıyordu; cidar 2,0 mm (hoop 1,8 mm, imalat tabanına
yükseltilmiş) yalnız düzyazı gerekçede ve STEP künyesinde geçiyordu. Kapak
ise analizde DİŞBÜKEY 1,81 mm, imalat katısında DÜZ 9,13 mm — fark yalnız
STEP künyesindeydi.

Ters-mutasyonlar: ``docs/scofield/raw/OH/D35/onemli-kati-cad/a1/mutasyon.py``.
"""

import math
import pathlib
import re

import pytest

from tests.support.form_defaults import form_yuku
from tests.test_example_projects import (ENDPOINTS, HEADERS, NAMES,
                                         calculate_payload, load_example_doc)

KOK = pathlib.Path(__file__).resolve().parents[1]

#: API ⟷ FORM yolu bağıl toleransı. İki yol aynı motoru anlatır; fark
#: yuvarlamadan büyük olamaz. %0,5 kaba ağdır — ölçülen kusur %10,5'ti.
YOL_BAGIL_TOLERANS = 0.005

#: Katı örneğin TAŞIMASI gereken form alanları (OH-ON-03 asgari kümesi).
#: Tek kaynak üretici betiktir; burada ikinci kez SAYI yazılmaz, yalnız
#: ADLAR sınanır.
from examples.generate_examples import (                     # noqa: E402
    KATI_ORNEGE_TASINAN_FORM_ALANLARI)

#: Segment boyu toleransı [mm] — üretici ile AYNI sabit (tek kaynak).
from hrma.export.step_export import (                        # noqa: E402
    GRAIN_SEGMENT_LENGTH_TOLERANCE_MM)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


def _kos(client, motor_type, yuk):
    r = client.post(ENDPOINTS[motor_type], json=yuk, headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    g = r.get_json()
    assert 'error' not in g, g.get('error')
    return g


_ONBELLEK = {}


def _kati_sonuc(client):
    """Katı örneğin API yolundaki tam yanıtı (motor tipi başına bir koşu)."""
    if 'solid' not in _ONBELLEK:
        alanlar = load_example_doc('solid')['inputs']['fields']
        _ONBELLEK['solid'] = _kos(client, 'solid',
                                  calculate_payload('solid', alanlar))
    return _ONBELLEK['solid']


# ---------------------------------------------------------------------------
# OH-ON-03 — API yolu ile FORM yolu AYNI sayıyı vermeli
# ---------------------------------------------------------------------------
#: motor tipi -> kıyaslanacak yapraklar (yanıtın kökünden okunur).
_YAPRAKLAR = {
    'solid': ('isp_sea_level', 'total_impulse', 'burn_time', 'max_thrust',
              'average_thrust', 'c_star', 'propellant_mass'),
    'liquid': ('isp_sea_level', 'isp_vacuum', 'thrust', 'c_star',
               'chamber_pressure'),
    'hybrid': ('isp', 'thrust', 'total_impulse', 'burn_time', 'c_star'),
}


def _yaprak_kaynagi(motor_type, govde):
    return govde.get('motor') if motor_type == 'hybrid' else govde


@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_ornek_API_ve_FORM_yollari_ayni_sayiyi_verir(client, motor_type):
    """Örneği yükleyip Hesapla'ya basmak, dosyadaki sayıyı DEĞİŞTİRMEMELİ.

    ÖLÇÜLDÜ (OH-ON-03): katı örnekte iki yol 51 alan farkla çağrılıyordu ve
    Isp 140,109 ⟷ 125,401 s ayrışıyordu. Hibrit ve sıvıda kayma yoktu
    (``12_once_hibrit_sivi.json``), bu yüzden üçü de burada sınanır: kusur
    yalnız katıda vardı ama sözleşme üç sayfanın da sözleşmesidir.
    """
    alanlar = load_example_doc(motor_type)['inputs']['fields']
    api = _yaprak_kaynagi(motor_type,
                          _kos(client, motor_type,
                               calculate_payload(motor_type, alanlar)))
    form = _yaprak_kaynagi(motor_type,
                           _kos(client, motor_type,
                                form_yuku(motor_type, alanlar)))
    sapan = []
    for y in _YAPRAKLAR[motor_type]:
        a, f = api.get(y), form.get(y)
        assert isinstance(a, (int, float)) and isinstance(f, (int, float)), (
            f'{motor_type}.{y}: iki yolun birinde sayı yok (api={a!r}, '
            f'form={f!r})')
        if not math.isclose(a, f, rel_tol=YOL_BAGIL_TOLERANS, abs_tol=1e-9):
            sapan.append(f'{y}: API {a:.6g} ⟷ FORM {f:.6g} '
                         f'(%{(f - a) / a * 100:+.4f})')
    assert not sapan, (
        f'{motor_type} örneği iki yolda farklı sayı veriyor — kullanıcı proje '
        'şeridinde bir sayı görüp Hesapla\'da başkasını alır:\n  '
        + '\n  '.join(sapan))


def test_kati_ornek_duyarli_form_alanlarini_tasiyor():
    """Katı örnek, sonucu oynatan form alanlarını dosyasında taşımalı.

    Bu, yukarıdaki davranış bekçisinin SEBEP tarafıdır: alan dosyadan
    düşerse iki yol yine ayrışır. Ters-mutasyon buraya bağlıdır.
    """
    alanlar = load_example_doc('solid')['inputs']['fields']
    eksik = [ad for ad in KATI_ORNEGE_TASINAN_FORM_ALANLARI
             if ad not in alanlar]
    assert not eksik, (
        f'katı örnek şu form alanlarını taşımıyor: {eksik}; örneği yeniden '
        'üretin (python3 examples/generate_examples.py)')


def test_kati_ornek_alan_degerleri_sablonun_kendi_varsayilani():
    """Taşınan değerler UYDURMA değil, ``solid.html``in kendi ``value=``si."""
    from tests.support.form_defaults import sayisal_varsayilanlar
    sablon = sayisal_varsayilanlar('solid')
    alanlar = load_example_doc('solid')['inputs']['fields']
    for ad in KATI_ORNEGE_TASINAN_FORM_ALANLARI:
        assert math.isclose(float(alanlar[ad]), sablon[ad], rel_tol=1e-12), (
            f'{ad}: örnekte {alanlar[ad]}, solid.html varsayılanı '
            f'{sablon[ad]} — örnek sayfanın varsayılanından ayrılmış')


# ---------------------------------------------------------------------------
# OH-ON-04 — STEP yakıt tanesi segmentleri
# ---------------------------------------------------------------------------
def _step_olc(yol):
    """Üretilen STEP dosyasını GERİ OKUYUP ölç (imalata giden gerçek katı)."""
    from build123d import import_step
    sekil = import_step(str(yol))
    katilar = sekil.solids()
    return [{'boy_mm': k.bounding_box().size.X,
             'hacim_mm3': k.volume,
             'yuzey_sayisi': len(k.faces()),
             'x_min': k.bounding_box().min.X,
             'x_max': k.bounding_box().max.X} for k in katilar]


@pytest.fixture(scope='module')
def kati_step(client, tmp_path_factory):
    """Katı örneğin imalat STEP dosyaları (bir kez üretilir)."""
    from hrma.export.step_export import generate_step_assembly
    dizin = tmp_path_factory.mktemp('d35_step')
    dosyalar = generate_step_assembly(_kati_sonuc(client),
                                      motor_type='solid',
                                      out_dir=str(dizin))
    assert 'fuel_grain' in dosyalar, dosyalar
    return dosyalar


def test_step_yakit_tanesi_segment_basina_ayri_kati_uretiyor(client,
                                                             kati_step):
    """Analiz N segment yayımlıyorsa STEP'te N ayrı katı olmalı.

    ÖLÇÜLDÜ (önce): 1 katı, 4 yüzey, kesintisiz 360 mm boru. Analiz
    ``number_of_segments = 3`` diyor ve Kn eğrisini 6 uç cepheden kuruyor.
    """
    gd = _kati_sonuc(client)['grain_design']
    n = int(gd['number_of_segments'])
    seg = float(gd['segment_length_mm'])
    assert n >= 2, 'bu bekçi çok segmentli örneği ölçer (örnek 3xBATES)'

    katilar = _step_olc(kati_step['fuel_grain'])
    assert len(katilar) == n, (
        f'analiz {n} segment yayımlıyor ama STEP {len(katilar)} katı '
        'taşıyor — imal edilen tane analiz edilen tane değil')
    for i, k in enumerate(katilar, 1):
        assert abs(k['boy_mm'] - seg) <= GRAIN_SEGMENT_LENGTH_TOLERANCE_MM, (
            f'{i}. segment {k["boy_mm"]:.4f} mm, analiz {seg:.4f} mm')
        # Halka silindir: dış yüzey + port yüzeyi + İKİ uç cephe.
        assert k['yuzey_sayisi'] == 4, (
            f'{i}. segment {k["yuzey_sayisi"]} yüzey taşıyor, halka silindir '
            '4 bekler (dış + port + iki uç)')
    # Yanma cephesi sayısı: her segmentin İKİ ucu yanar -> 2N.
    assert sum(1 for _ in katilar) * 2 == 2 * n


def test_step_yakit_tanesi_hacmi_analizin_itici_kutlesiyle_uyusuyor(
        client, kati_step):
    """Katıların toplam hacmi = itici kütlesi / yoğunluk (%1 içinde).

    Segmentlere bölmek İTİCİYİ DEĞİŞTİRMEMELİDİR; bu düğüm onu kilitler.
    """
    sonuc = _kati_sonuc(client)
    alanlar = load_example_doc('solid')['inputs']['fields']
    yogunluk = float(alanlar['density'])                 # kg/m³
    kutle = float(sonuc['propellant_mass'])              # kg
    beklenen_mm3 = kutle / yogunluk * 1e9
    olculen = sum(k['hacim_mm3'] for k in _step_olc(kati_step['fuel_grain']))
    assert math.isclose(olculen, beklenen_mm3, rel_tol=0.01), (
        f'STEP itici hacmi {olculen:.1f} mm³, analizin kütlesinden '
        f'({kutle:.6f} kg / {yogunluk:.1f} kg/m³) beklenen '
        f'{beklenen_mm3:.1f} mm³')


def test_step_kunyesi_segment_beyani_tasiyor(kati_step):
    """STEP künyesi segment sayısını ve boşluk hükmünü ADIYLA söylemeli.

    ÖLÇÜLDÜ (önce): ``FILE_NAME`` segment sayısı hakkında HİÇBİR beyan
    taşımıyordu. Dosyayı açan imalatçı, üç parçayı mı yoksa tek boruyu mu
    yapacağını künyeden okuyamıyordu.
    """
    metin = pathlib.Path(kati_step['fuel_grain']).read_text(
        'utf-8', errors='replace')
    baslik = metin[:metin.find('DATA;')]
    assert re.search(r'\d+\s+separate BATES segments', baslik), baslik[:800]
    assert 'end faces' in baslik, baslik[:800]
    assert 'number_of_segments' in baslik, baslik[:800]
    # Boşluk ya yayımlanmıştır ve yazılır, ya da yayımlanmadığı SÖYLENİR.
    assert ('inter-segment gap' in baslik), baslik[:800]
    # Katı sayısı dosyada da görünür (her segment kendi MANIFOLD_SOLID_BREP'i).
    kac = len(re.findall(r'MANIFOLD_SOLID_BREP', metin))
    assert kac >= 2, f'STEP {kac} katı gövde taşıyor, segmentler ayrı değil'


def test_segment_plani_tane_boyuyla_celisirse_kati_uretilmez():
    """N x segment_length, grain_length ile uyuşmazsa üretim REDDEDİLİR.

    Fail-closed (Doktrin 1): iki ayrı tane boyu yayımlanmışsa hangisinin
    imalata gideceği KAZANILMAMIŞTIR; sayı seçilmez, üretim durur.
    """
    from hrma.export.step_export import _grain_segment_plan
    plan = _grain_segment_plan({'grain_design': {
        'number_of_segments': 3, 'segment_length_mm': 120.0}})
    assert plan['n'] == 3 and plan['segment_mm'] == 120.0
    assert plan['gap_published'] is False
    assert plan['stack_mm'] == 360.0
    # ÖH D37 A1a pdf-grafik-step · DV36-05: çözücü boşluğu yayımlıyor
    # (grain_gap_source); bu gövde alanı TAŞIMIYOR -> 'yanıtta yok' kolu.
    assert 'absent_in_response' in plan['source']
    # Segment bilgisi yoksa plan KAZANILMAZ (tek parça + beyan kolu).
    assert _grain_segment_plan({'grain_design': {'grain_length_mm': 360}}) \
        is None
    # Boşluk yayımlanırsa yığın boyu onu GÖRÜR.
    plan2 = _grain_segment_plan({'grain_design': {
        'number_of_segments': 3, 'segment_length_mm': 120.0,
        'grain_gap_mm': 2.0}})
    assert plan2['gap_published'] is True
    assert plan2['stack_mm'] == pytest.approx(364.0)


# ---------------------------------------------------------------------------
# OH-ON-05 — varsayım künyesi ve kapak beyanı
# ---------------------------------------------------------------------------
def test_kati_ucu_cozucunun_boyutlandirdigi_cidari_beyan_ediyor(client):
    """``case_thickness`` boşken cidar MAKİNE-OKUR bir alanda beyan edilmeli.

    ÖLÇÜLDÜ (önce): imalata giden 2,0 mm'lik cidarın kullanıcı girdisi
    olmadığı yalnız ``case_analysis.safety_factor_basis`` DÜZYAZISINDA ve
    STEP künyesinde yazıyordu; yanıtı okuyan hiçbir tüketici bunu alan
    adından öğrenemiyordu.

    Kanal neden ``defaults_applied`` DEĞİL: o kanalın ÖK-19 sözleşmesi dar
    tanımlıdır (anahtar kümesi, ``reason`` sözlüğü, tek kurucu, tam yükte
    hiç yazılmama) ve dört bekçiyle kilitlidir; cidar kalınlığı bir GİRDİ
    VARSAYILANI değil yapısal modelin ÇIKARDIĞI bir tasarım değeridir.
    Beyan kardeş kanaldadır (``case_geometry``), ``head_geometry`` gibi.
    """
    sonuc = _kati_sonuc(client)
    alanlar = load_example_doc('solid')['inputs']['fields']
    assert 'case_thickness' not in alanlar, (
        'bu bekçi cidarın BOŞ bırakıldığı koşumu ölçer')
    cg = sonuc.get('case_geometry')
    assert isinstance(cg, dict) and cg, 'case_geometry beyanı yok'
    kasa = sonuc['structural_analysis']['case_analysis']
    # TEK KAYNAK: beyan yapısal analizin sayısını tekrarlar, üretmez.
    assert cg['wall_thickness_mm'] == pytest.approx(kasa['wall_thickness_mm'])
    assert cg['hoop_required_mm'] == pytest.approx(
        kasa['wall_thickness_hoop_required_mm'])
    assert cg['manufacturing_floor_mm'] == pytest.approx(
        kasa['wall_thickness_manufacturing_floor_mm'])
    # Kullanıcı vermedi -> HRMA boyutlandırdı, beyan bunu SÖYLEMELİ.
    assert cg['user_supplied'] is False
    assert cg['thickness_source'] in ('sized_by_hrma', 'manufacturing_floor')
    assert 'not your input' in cg.get('note', '').lower()
    assert cg['source'] == 'structural_analysis.case_analysis'


def test_cidar_beyani_OK19_kunye_sozlesmesini_KIRLETMIYOR(client):
    """Cidar beyanı ``defaults_applied`` kanalına sızmamalı.

    D26/D27'nin kazandığı sözleşme: ``defaults_applied`` YALNIZ uç/öğretici
    girdi varsayılanlarını taşır ve iki uçta AYNI biçimdedir. Cidar oraya
    yazılsaydı ``reason`` sözlüğü ve anahtar kümesi genişler, aynı ad iki
    biçimde yayımlanırdı.
    """
    kunye = _kati_sonuc(client).get('defaults_applied') or []
    assert not [k for k in kunye if k.get('field') == 'case_thickness'], (
        'cidar beyanı ÖK-19 künye kanalına sızmış')
    for k in kunye:
        assert set(k) == {'field', 'value', 'reason', 'applied_by',
                          'message'}, k
        assert k['reason'] in ('tutorial_default', 'endpoint_default'), k


def test_kati_ucu_kapak_geometrisini_iki_degeriyle_beyan_ediyor(client):
    """Analizin kapağı ile imalat katısının kapağı yanıtta YAN YANA olmalı.

    ÖLÇÜLDÜ (önce): ``head_geometry`` yanıtta YOKTU; analiz DİŞBÜKEY
    1,81 mm derken imalat katısı DÜZ 9,13 mm çiziyordu ve fark yalnız STEP
    künyesinde geçiyordu.
    """
    sonuc = _kati_sonuc(client)
    hg = sonuc.get('head_geometry')
    assert isinstance(hg, dict) and hg, 'head_geometry beyanı yok'
    if hg.get('status') == 'not_established':
        pytest.fail('bu örnekte kapak analizi var; beyan kazanılmalıydı: '
                    + str(hg.get('reason')))
    kapak = sonuc['structural_analysis']['end_cap_analysis']
    assert hg['analysis']['thickness_mm'] == pytest.approx(
        kapak['head_thickness_used_mm'])
    assert hg['analysis']['type'] == kapak['head_thickness_used_type']
    assert hg['cad_model']['type'] == 'flat'
    assert hg['cad_model']['thickness_mm'] == pytest.approx(
        kapak['flat_head_thickness'])
    # İki sayı GERÇEKTEN farklı olmalı ki beyan bir şey söylesin.
    assert hg['cad_model']['thickness_mm'] != hg['analysis']['thickness_mm']
    assert 'end_cap_analysis' in hg['source']


def test_kapanis_civatasi_verilmediginde_varsayilan_UYDURULMUYOR(client):
    """Cıvata sayısı yoksa birleşim boyutlandırılmaz — fail-closed.

    ÖLÇÜLDÜ: ``closure_bolt_count`` gönderilmediğinde çözücü bir varsayılan
    UYGULAMAZ; bu yüzden ``defaults_applied``da da anılmamalıdır (olmayan
    bir değeri beyan etmek yanlış olurdu). Doğru beyan kanalı
    ``assembly_integrity.closure_joint``tir.
    """
    sonuc = _kati_sonuc(client)
    kunye = sonuc.get('defaults_applied') or []
    assert not [k for k in kunye if k.get('field') == 'closure_bolt_count'], (
        'uygulanmamış bir varsayılan defaults_applied\'a yazılmış')
    birlesim = (sonuc['structural_analysis']['assembly_integrity']
                .get('closure_joint') or {})
    assert birlesim.get('status') == 'not_sized', birlesim
    assert 'bolt count' in (birlesim.get('basis') or '').lower()


if __name__ == '__main__':                  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, '-v']))
