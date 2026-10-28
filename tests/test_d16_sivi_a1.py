"""ÖH Dalga-16 · sıvı kulvarı · aşama 1 — onarım bekçileri.

Her sınıf TEK kalemi tutar ve her iddia, kusurun TERSİ enjekte edildiğinde
kırmızıya döndüğü ÖLÇÜLEREK yazılmıştır (ters-mutasyon kaydı:
``docs/scofield/raw/OH/D16/sivi/a1/mutasyon.txt``).

Kalemler
--------
OH-Z5-17  ``optimum_of_ratio``da İKİ tepe-Isp tablosu çelişiyordu
          (``peak_vac_isp`` ⟷ ``_liquid_reference``); 8 çiftin 8'i iki
          farklı sayı taşıyordu ve sıvı dal yalnız YAKITLA eşleşerek
          tablo-dışı çiftlere sessizce sayı uyduruyordu.
OH-Z4-01  İhraç 'doğrulandı' damgası sıvıda KAZANILAMIYORDU:
          ``CHAMBER_WALL_SF_SCHEMAS['chamber_structure']['measured_keys']``
          boştu ve ölçüm süzgeci blok düzeyindeki ``safety_factor_source``a
          bakıyordu (anahtar-başına olmalıydı).
OH-Z5-01  Sıvı zinciri toparlanma sıcaklığını (T_recovery) yayımlamıyordu:
          rejeneratif koşumda yanıtın tamamında ``T_recovery_K`` yolu 0
          adetti (kardeş hibritte 9).
P16B4-07  ``/api/detailed-cad/liquid`` boş istek: kalem ÖLÇÜMLE ÇÜRÜDÜ
          (uç bugün 422 veriyor); bu sınıf kazanılmış davranışı KİLİTLER.
"""
import math

import pytest

from hrma.export import cad_visualization as cv
from hrma.utils import optimum_of_ratio as oor


# ---------------------------------------------------------------------------
# Ortak fikstürler
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def finder():
    return oor.OptimumOFRatioFinder()


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _sivi_yuk(**ek):
    yuk = {
        'motor_name': 'D16-SIVI-A1', 'thrust': 10000.0, 'burn_time': 30.0,
        'chamber_pressure': 30.0, 'mixture_ratio': 2.2,
        'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'expansion_ratio': 12.0,
    }
    yuk.update(ek)
    return yuk


@pytest.fixture(scope='module')
def sivi_size(client):
    r = client.post('/calculate_liquid', json=_sivi_yuk())
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def sivi_verify(client):
    """Kalınlığı KULLANICI verdi -> ``design_mode == 'verify'``."""
    # V301/L-KABUK: rejeneratif cidar iki katmanlı — basıncı taşıyan dış
    # kabuğun kalınlığını da KULLANICI verince doğrulama kipidir (astar
    # chamber_wall_thickness, kabuk closeout_thickness).
    r = client.post('/calculate_liquid', json=_sivi_yuk(
        chamber_wall_thickness=3.0, closeout_thickness=6.0,
        safety_factor=2.0))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


# L-B (v3.0.1, SV-05): yapı hükmü artık ÇÖZÜLMÜŞ cidar sıcaklığında
# verilir. Yukarıdaki iki fikstürde (2-3 mm cidar, RP-1 rejeneratif) istasyon
# marşı tepe cidarı erime üstünde çözüyor -> hüküm geri çekilir ve
# ``safety_factor_basis`` geçerlilik-dışı tanı metnine döner (beklenen,
# LIQUID_MODEL_VALIDITY_SAFETY_FACTOR_BASIS). Kipe göre kurulan cümlenin
# bekçileri GEÇERLİLİK İÇİ koşumda koşar: verify -> 8 mm cidar (marş ince
# cidar zarfı dışında, hüküm beyanlı hedef sıcaklıkta); size -> film tipi
# (1B cidar çözücüsü yok, aynı beyan).
@pytest.fixture(scope='module')
def sivi_verify_gecerli(client):
    r = client.post('/calculate_liquid', json=_sivi_yuk(
        chamber_wall_thickness=8.0, closeout_thickness=6.0,
        safety_factor=2.0))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    j = r.get_json()
    assert j['structural_analysis']['chamber_structure'][
        'model_validity_limit_exceeded'] is False
    return j


@pytest.fixture(scope='module')
def sivi_size_gecerli(client):
    r = client.post('/calculate_liquid', json=_sivi_yuk(
        cooling_type='film_cooling', film_cooling_percent=5.0))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    j = r.get_json()
    assert j['structural_analysis']['chamber_structure'][
        'model_validity_limit_exceeded'] is False
    return j


def _yollar(dugum, yol=''):
    if isinstance(dugum, dict):
        for k, v in dugum.items():
            yield from _yollar(v, yol + '/' + str(k))
    elif isinstance(dugum, list):
        for v in dugum:
            yield from _yollar(v, yol + '/[]')
    else:
        yield yol, dugum


# ---------------------------------------------------------------------------
# OH-Z5-17 — tepe Isp TEK KAYNAK
# ---------------------------------------------------------------------------
class TestZ517TepeIspTekKaynak:
    """Sıvı dalın tepe Isp'si ``peak_vac_isp``ten GELMELİ, kopyası olmamalı."""

    CIFTLER = [('lox', 'lh2'), ('lox', 'rp1'), ('lox', 'methane'),
               ('lox', 'ch4'), ('lox', 'htpb'), ('n2o', 'htpb'),
               ('n2o4', 'mmh'), ('n2o4', 'udmh')]

    @pytest.mark.parametrize('ox,fu', CIFTLER)
    def test_liquid_reference_tabloyla_ayni_sayiyi_verir(self, finder, ox, fu):
        """İki tablo AYNI çift için AYNI tepe Isp'yi söylemek zorunda.

        Kusur hâli (ölçüldü, ``once.json``): 8 çiftin 8'inde ayrışma vardı;
        en büyüğü N2O/HTPB 250 ⟷ 320.
        """
        beklenen = finder.peak_vac_isp[(ox, fu)]
        tepe_isp, _optimum_of = finder._liquid_reference(ox, fu)
        assert tepe_isp == beklenen, (
            f'{ox}/{fu}: sıvı dal {tepe_isp} s diyor, künyeli tablo '
            f'{beklenen} s diyor — iki tepe Isp tablosu yine ayrıştı.')

    @pytest.mark.parametrize('ox,fu', CIFTLER)
    def test_liquid_reference_optimum_of_tabloyla_ayni(self, finder, ox, fu):
        """Tepe O/F de ``theoretical_optimums``un kopyası olmamalı."""
        beklenen = finder.theoretical_optimums[(ox, fu)]
        _tepe_isp, optimum_of = finder._liquid_reference(ox, fu)
        assert optimum_of == beklenen, (
            f'{ox}/{fu}: sıvı dal O/F {optimum_of}, tablo {beklenen}.')

    @pytest.mark.parametrize('ox,fu', [
        ('n2o', 'rp1'),          # yakıt tanıdık, ÇİFT tabloda yok
        ('n2o4', 'lh2'),         # yakıt tanıdık, ÇİFT tabloda yok
        ('h2o2', 'methane'),     # yakıt tanıdık, oksitleyici hiç tanınmıyor
    ])
    def test_tablo_disi_cift_fail_closed(self, finder, ox, fu):
        """Yalnız YAKITLA eşleşip sayı uydurmak YASAK (sessiz varsayılan).

        Kusur hâli: ``n2o/rp1`` sessizce LOX/RP-1'in (350 s, O/F 2,77)
        çiftini döndürüyordu.
        """
        with pytest.raises(ValueError):
            finder._liquid_reference(ox, fu)

    def test_kaynakta_ciplak_tepe_isp_literali_yok(self):
        """Eski kopya sayılar KODA geri yazılmamalı (tek kaynak koruması)."""
        import inspect
        kaynak = inspect.getsource(oor.OptimumOFRatioFinder._liquid_reference)
        govde = kaynak.split('"""')[-1]      # docstring'i dışarıda bırak
        for literal in ('450', '350', '380', '320'):
            assert literal not in govde, (
                f'``_liquid_reference`` gövdesine {literal} çıplak literali '
                'geri gelmiş — tepe Isp yine iki yerde yazılı.')


# ---------------------------------------------------------------------------
# OH-Z4-01 — ihraç doğrulama damgası
# ---------------------------------------------------------------------------
class TestZ401IhracDogrulamaDamgasi:

    def test_sema_hazne_blogu_olculmus_sf_adayi_tanir(self):
        """``chamber_structure`` şeması BOŞ ``measured_keys`` taşıyamaz."""
        anahtarlar = cv.CHAMBER_WALL_SF_SCHEMAS['chamber_structure'][
            'measured_keys']
        assert 'hoop_safety_factor' in anahtarlar, (
            'Şema, çizilen cidarda hesaplanan SF adayını tanımıyor; ihraç '
            'katmanı doğrulama iddiasını hiçbir koşuda kazanamaz.')

    def test_olcum_suzgeci_anahtar_basinadir(self):
        """Blok düzeyi ``safety_factor_source`` KARDEŞ alanı elememeli.

        Kusur hâli: kullanıcı bir SF HEDEFİ girince blok künyesi "user input
        (safety factor)" oluyordu ve bu tek cümle, çizilen cidarda ölçülen
        ``hoop_safety_factor``ı da girdi sayıp eliyordu.
        """
        blok = {
            'hoop_safety_factor': 9.9,
            'safety_factor': 2.0,
            'safety_factor_source': 'user input (safety factor)',
            'design_mode': 'verify',
            'safety_factor_is_tautological': False,
        }
        sf, olculdu, hedef, _basis = cv._wall_safety_factor(
            blok, 'chamber_structure')
        assert sf == pytest.approx(9.9)
        assert olculdu is True, (
            'Kullanıcının SF hedefi künyesi, ölçülmüş hoop SF adayını '
            'eliyor — süzgeç yine blok düzeyinde.')
        assert hedef == pytest.approx(2.0)

    def test_alanin_kendi_kunyesi_hala_eliyor(self):
        """Anahtar-başına süzgeç, KENDİ künyesini görmezden GELMEMELİ."""
        blok = {
            'hoop_safety_factor': 9.9,
            'hoop_safety_factor_source': 'user input',
            'design_mode': 'verify',
            'safety_factor': 2.0,
        }
        _sf, olculdu, _hedef, _basis = cv._wall_safety_factor(
            blok, 'chamber_structure')
        assert olculdu is not True, (
            'Alanın KENDİ künyesi "girdi" diyorken ölçüm iddia edildi.')

    def test_verify_kipinde_damga_kazanilir(self, sivi_verify):
        """Kalınlığı kullanıcı verdiyse ihraç DOĞRULAMA iddia edebilmeli."""
        blok = sivi_verify['structural_analysis']['chamber_structure']
        assert blok['design_mode'] == 'verify'
        _sf, olculdu, _hedef, _basis = cv._wall_safety_factor(
            blok, 'chamber_structure')
        assert olculdu is True, (
            'verify kipinde bile "NOT A VERIFICATION" basılıyor.')

    def test_size_kipinde_damga_kazanilmaz(self, sivi_size):
        """Kalınlığı HRMA seçtiyse doğrulama iddiası YAPILMAMALI."""
        blok = sivi_size['structural_analysis']['chamber_structure']
        assert blok['design_mode'] == 'size'
        _sf, olculdu, _hedef, _basis = cv._wall_safety_factor(
            blok, 'chamber_structure')
        assert olculdu is False

    def test_verify_kunyesi_sized_cumlesi_kurmaz(self, sivi_verify_gecerli):
        """verify kipinde "cidar hedefe boyutlandırıldı" cümlesi YANLIŞTIR."""
        basis = sivi_verify_gecerli['structural_analysis'][
            'chamber_structure']['safety_factor_basis']
        assert 'this one is a verification' in basis
        assert 'the wall was sized so that' not in basis, (
            'Aynı künye hem "cidar hedefe boyutlandırıldı" hem "bu bir '
            'doğrulamadır" diyor — çelişik cümle geri gelmiş.')

    def test_size_kunyesi_sized_cumlesini_korur(self, sivi_size_gecerli):
        """size kipinde cümle DEĞİŞMEMELİ (onarım kapsamı dar)."""
        basis = sivi_size_gecerli['structural_analysis'][
            'chamber_structure']['safety_factor_basis']
        assert 'the wall was sized so that' in basis


# ---------------------------------------------------------------------------
# OH-Z5-01 — toparlanma sıcaklığı
# ---------------------------------------------------------------------------
class TestZ501ToparlanmaSicakligi:

    def test_rejeneratif_kosumda_T_recovery_yayimlanir(self, sivi_size):
        """Rejeneratif sıvıda ``T_recovery_K`` yolu SIFIR olamaz.

        Kusur hâli (ölçüldü): rejeneratif yanıtta 0 yol, hibritte 9.

        ÖH D21 bekci-cevirisi a1 (OH-D17-12) — YOL DEĞİL DEĞER SAYILIYOR.
        ESKİ hâl (ölçüldü, ``once_statik.json``: ``yalniz_yol_sayiyor``
        True / ``deger_sinaniyor`` False) yalnız ANAHTAR YOLUNU sayıyordu:
        ``T_recovery_K = None`` yayımlayan bir ürün de bu bekçiyi
        geçerdi, oysa panel yine kendi varsayılanında kalırdı. Değerin
        kendisi de sınanır (ölçüldü: 3434,178895 K, kaynak 'assumed').
        """
        yollar = [(p, v) for p, v in _yollar(sivi_size)
                  if 'T_recovery_K' in p]
        assert yollar, (
            'Sıvı zinciri hiçbir yerde T_recovery yayımlamıyor; koruma '
            'paneli panel varsayılanında kalır.')
        for yol, deger in yollar:
            assert isinstance(deger, (int, float)) and not isinstance(
                deger, bool), (
                f'{yol} sayı değil ({deger!r}) — anahtar var, hüküm yok')
            assert math.isfinite(float(deger)) and float(deger) > 0.0, (
                f'{yol} = {deger!r}; sürücü sıcaklık pozitif ve sonlu '
                f'olmalı (yoksa panel varsayılanında kalır)')

    def test_T_recovery_hazne_sicakligiyla_ayni(self, sivi_size):
        """Sürücü sıcaklık ZİNCİRİN KENDİ T_c'si olmalı — ikinci sayı değil."""
        gaz = sivi_size['heat_transfer_analysis']['gas_side_analysis']
        assert gaz['T_recovery_K'] == pytest.approx(
            sivi_size['chamber_temperature'], rel=1e-12), (
            'Yayımlanan sürücü sıcaklık, zincirin kullandığı hazne '
            'sıcaklığından farklı — ikinci bir T_aw varsayımı doğmuş.')

    def test_T_recovery_kunyesi_var(self, sivi_size):
        gaz = sivi_size['heat_transfer_analysis']['gas_side_analysis']
        assert gaz.get('T_recovery_basis'), 'Sürücü sıcaklık künyesiz.'

    def test_kamara_h_gas_kaynagi_ve_kunyesi_dallanmayla_uyumlu(
            self, sivi_size):
        """Kamara katsayısının YAYIMLANMA HÜKMÜ cidar kaynağıyla uyumlu mu?

        ÖH D21 bekci-cevirisi a1 (OH-D17-12) — TOTOLOJİ SÖKÜLDÜ.
        ESKİ bekçi (``test_kamara_h_gas_akiyla_tutarli``) tek iddia
        taşıyordu: ``h_g*(T_rec - T_cidar) == q_kamara``. O özdeşlik
        ÜRÜNDE KURULUYOR — ``hrma/engines/liquid_rocket_engine.py``
        ``gas_side['gas_side_coefficient_chamber'] = q_chamber_kw *
        1000.0 / delta`` — yani cebirsel olarak KAPALI: hiçbir ürün
        değişikliği onu kıramaz. Ölçüldü (``once_dinamik.json``
        ``OH-D17-12``): bağıl hata **tam 0.0**, ``ozdeslik_totoloji_mi``
        True. Özdeşlik KORUNUYOR (bölmenin sağlamlık kontrolü olarak
        değeri var) ama artık TEK iddia değil; yanına ürünün gerçekten
        kırılabilir üç sözleşmesi konuyor:

          1. KAYNAK+BİRİM: yayımlanan ``chamber_heat_flux`` [W/m²],
             ``cooling_system.chamber_heat_flux`` [kW/m²] değerinin tam
             1000 katıdır — akı burada İKİNCİ bir Bartz koşumundan
             türetilmez (ölçüldü: oran tam 1,0).
          2. DALLANMA: ``wall_temperature_source`` ÇÖZÜLMÜŞ marş ise
             katsayı yayımlanmaz (``NOT_PUBLISHED``) ve etkin katsayı
             yalnız açık adıyla taşınır; VARSAYILMIŞ ise yayımlanır ve
             künyesi bunu söyler (fail-closed beyan sözleşmesi).
          3. BÖLEN: ``T_recovery - T_cidar_sicak`` pozitif ve künye
             ``recovered from`` diyorsa katsayı da pozitif olmalı.
        """
        htx = sivi_size['heat_transfer_analysis']
        gaz = htx['gas_side_analysis']
        cool = sivi_size.get('cooling_system') or {}
        q = gaz.get('chamber_heat_flux')
        durum = gaz.get('gas_side_coefficient_chamber_status')
        h_g = gaz.get('gas_side_coefficient_chamber')
        kaynak = str(cool.get('wall_temperature_source') or '').lower()

        # (1) KAYNAK + BİRİM çaprazı — bağımsız, ikinci Bartz'ı yakalar.
        #
        # ÖH D26 / OH-D25-21 (zincir OH-D17-12): bu çapraz eskiden
        # ``if q is not None and q_kw:`` koşuluna bağlıydı, yani ürün iki
        # yapraktan HERHANGİ BİRİNİ yayımlamayı bıraksa (ya da ``q_kw`` 0,0
        # dönse — ``and q_kw`` sıfırı da yanlış sayıyordu) çapraz SESSİZCE
        # atlanıyor ve test yeşil kalıyordu. Bekçinin kendisi ölü adam
        # düğmesiydi. ÖLÇÜLDÜ (``a2/once.json`` ``OH-D25-21``): bu ağaçta
        # iki yaprak da var (7011230,019 W/m² ⟷ 7011,230 kW/m², oran tam
        # 1000). Dolayısıyla varlık koşulu ARTIK İDDİADIR: yaprağın
        # kaybolması kırmızı vermelidir (fail-closed).
        q_kw = cool.get('chamber_heat_flux')
        assert q is not None, (
            'heat_transfer_analysis.gas_side_analysis.chamber_heat_flux '
            'yayımlanmıyor — birim çaprazının ölçtüğü yaprak kayboldu; '
            'çapraz sessizce atlanamaz (OH-D25-21)')
        assert q_kw is not None, (
            'cooling_system.chamber_heat_flux yayımlanmıyor — birim '
            'çaprazının ikinci yaprağı kayboldu; çapraz sessizce '
            'atlanamaz (OH-D25-21)')
        assert float(q_kw) > 0.0, (
            f'cooling_system.chamber_heat_flux {q_kw!r} kW/m² — pozitif '
            f'olmayan akı çaprazı anlamsız kılar ve eski koşul '
            f'({"and q_kw"!r}) bunu sessizce atlıyordu (OH-D25-21)')
        assert float(q) == pytest.approx(float(q_kw) * 1000.0,
                                         rel=1e-9), (
            f'gas_side.chamber_heat_flux {q!r} W/m², '
            f'cooling_system.chamber_heat_flux {q_kw!r} kW/m² — '
            f'akı ikinci bir kaynaktan geliyor ya da birim çevrimi '
            f'bozuk')

        # (2) DALLANMA sözleşmesi.
        if 'solved' in kaynak:
            assert h_g is None and durum == 'NOT_PUBLISHED', (
                f'cidar ÇÖZÜLMÜŞ marşla geldi ({kaynak!r}) ama kamara '
                f'katsayısı {h_g!r} / {durum!r} olarak yayımlanıyor — '
                f'o sayı Bartz kamara katsayısı DEĞİLDİR')
            assert 'gas_side_effective_chamber_coefficient_if_march' in gaz, (
                'marşlı koşumda etkin katsayı açık adıyla taşınmıyor')
            return
        if h_g is None:
            assert durum == 'NOT_PUBLISHED', (
                f'katsayı yok ama durum {durum!r} — yokluk adıyla '
                f'beyan edilmiyor')
            assert gaz.get('gas_side_coefficient_chamber_basis'), (
                'yayımlanmama gerekçesi künyesiz')
            return

        assert durum == 'PUBLISHED'
        kunye = str(gaz.get('gas_side_coefficient_chamber_basis') or '')
        assert 'recovered from' in kunye, (
            f'katsayı yayımlanıyor ama künye onun akıdan geri çözüldüğünü '
            f'söylemiyor: {kunye[:200]!r}')

        # (3) BÖLEN + özdeşlik (özdeşlik ÜRÜNDE kurulu; bölmenin
        #     sağlamlığını ve alanların birbirine bağlı kaldığını ölçer).
        t_rec = gaz['T_recovery_K']
        t_hot = htx['wall_analysis']['design_target_wall_temperature_hot_K']
        assert t_rec - t_hot > 0.0, (
            f'sürücü-cidar farkı pozitif değil ({t_rec!r} - {t_hot!r}); '
            f'katsayı yine de yayımlanmış')
        assert h_g > 0.0
        assert h_g * (t_rec - t_hot) == pytest.approx(q, rel=1e-9)


# ---------------------------------------------------------------------------
# P16B4-07 — kalem ÇÜRÜDÜ; kazanılmış kapı kilitlenir
# ---------------------------------------------------------------------------
class TestP16B407DetayliCadKapisi:

    @pytest.mark.parametrize('yuk', [{}, {'chamber_diameter': None}])
    def test_bos_istek_uydurma_olcu_uretmez(self, client, yuk):
        """Boş gövde 200 + üreticinin yedek ölçüleriyle dönemez."""
        r = client.post('/api/detailed-cad/liquid', json=yuk)
        assert r.status_code == 422, (
            f'Boş istek {r.status_code} döndü; kapı düşmüş.')
        j = r.get_json()
        assert j.get('status') == 'error'
        assert 'geometry' in str(j.get('error'))
        assert not j.get('dimensions'), (
            'Reddedilen istekte ölçü bloğu var — uydurma geometri sızıyor.')

    def test_gecerli_istek_hala_cizilir(self, client):
        """Kapı sağlıklı isteği KESMEMELİ (fail-closed ≠ fail-always).

        ÖH D23 fix-20 — istek TAMAMLANDI, kapı gevşetilmedi. Bu test üç
        ölçü yolluyordu ve 200 alıyordu; ``5cca01d`` (ÖH D22 ihracat a1,
        defter OH-D19-03) ``DetailedCADGenerator``ın yardımcı yollarındaki
        uydurma yedekleri de söktü. ÖLÇÜLDÜ (taban ef527ae): üç ölçülü
        istek 422 ``exit_diameter_not_available``, dördüncüsü eklenince
        422 ``nozzle_length_not_available`` veriyor — çünkü eski kod bu
        ikisi için Ø80 mm / 150 mm'lik VARSAYILANLAR çiziyordu ve çizim
        kullanıcının motoru değildi. Ret DOĞRU davranıştır; yanlış olan,
        lülesi tarif edilmemiş bir motorun "çizilebilir" sayılmasıydı.

        Bu yüzden testin iddiası korunur ama girdi lülenin GERÇEKTEN
        tarif edildiği hâle çekilir: beş ölçü verilince uç 200 döner ve
        ölçü bloğu verilen sayıların AYNISINI yankılar (uydurma yok).
        """
        yuk = {'chamber_diameter': 100.0, 'chamber_length': 200.0,
               'throat_diameter': 30.0, 'exit_diameter': 60.0,
               'nozzle_length': 150.0}
        r = client.post('/api/detailed-cad/liquid', json=yuk)
        assert r.status_code == 200, r.get_json()
        olculer = r.get_json()['dimensions']
        for ad, deger in yuk.items():
            assert olculer[ad] == deger, (ad, olculer.get(ad), deger)

    def test_lule_olcusu_eksikse_ADIYLA_reddedilir(self):
        """Eksik lüle ölçüsü sessiz varsayılanla DEĞİL, adıyla reddedilir.

        ÖH D23 fix-20: yukarıdaki istek tamamlanınca "eksik ölçü ne olur"
        sorusu ölçüsüz kalırdı. Kapının sıkılaşması burada kilitlenir —
        yoksa ileride bir yedek geri gelse test bunu göremezdi.
        """
        from hrma.app import app as _app
        istemci = _app.test_client()
        tam = {'chamber_diameter': 100.0, 'chamber_length': 200.0,
               'throat_diameter': 30.0, 'exit_diameter': 60.0,
               'nozzle_length': 150.0}
        for eksik in ('exit_diameter', 'nozzle_length'):
            yuk = {k: v for k, v in tam.items() if k != eksik}
            r = istemci.post('/api/detailed-cad/liquid', json=yuk)
            assert r.status_code == 422, (eksik, r.status_code)
            j = r.get_json()
            assert eksik in str(j.get('message')), (eksik, j)
            assert [f['field'] for f in j.get('invalid_fields', [])] \
                == [eksik], (eksik, j)
            assert not j.get('dimensions'), (eksik, j)


# ---------------------------------------------------------------------------
# OH-Z1-01 — 1220 kg/m³ öğreten katman + ölü alan
# ---------------------------------------------------------------------------
import os                                                    # noqa: E402

import hrma                                                  # noqa: E402

_HRMA_KOK = os.path.dirname(os.path.abspath(hrma.__file__))


def _oku(goreli):
    with open(os.path.join(_HRMA_KOK, goreli), encoding='utf-8') as f:
        return f.read()


class TestZ101N2OYogunlukOgretisi:
    """UI/i18n katmanı N₂O için DEPOLAMA yoğunluğu diye 1220 öğretemez.

    1220 kg/m³, N₂O'nun NORMAL KAYNAMA NOKTASI (184,67 K) değeridir; 20 °C
    doymuş sıvı 785,10 kg/m³'tür (+%55,4). Ürün zinciri Z1'de düzeldi ama
    ipucu metinleri bayat kalmıştı.
    """

    METIN_DOSYALARI = ('templates/advanced.html',
                       'static/js/i18n_advanced.js')

    #: Yoğunluk ipucunun i18n anahtarı — HTML gövdesinde de bu ad geçer.
    ANAHTAR = 'adv.tip.densityKgM'

    def _ipucu_satirlari(self, goreli):
        satirlar = [s for s in _oku(goreli).splitlines()
                    if self.ANAHTAR in s]
        assert satirlar, f'{goreli}: yoğunluk ipucu anahtarı kaybolmuş.'
        return satirlar

    @pytest.mark.parametrize('goreli', METIN_DOSYALARI)
    def test_1220_depolama_degeri_diye_sunulmuyor(self, goreli):
        """İddia SATIR BAZINDA: bir dilin metni düzelip öbürü bayat kalamaz.

        1220 sayısı ipucunda GEÇEBİLİR, ama yalnız "bu bir depolama değeri
        DEĞİLDİR" cümlesiyle birlikte. Aynı satırda başka bir yerde
        "boiling" kelimesinin bulunması YETMEZ (ölçüldü: ilk sürüm bekçisi
        ters-mutasyonda YEŞİL kaldı, çünkü cümlenin kuyruğu duruyordu).
        """
        for satir in self._ipucu_satirlari(goreli):
            if '1220' not in satir:
                continue
            assert ('not a storage value' in satir
                    or 'depolama değeri değildir' in satir), (
                f'{goreli}: ipucu 1220 sayısını "depolama değeri değil" '
                'demeden basıyor.')

    @pytest.mark.parametrize('goreli', METIN_DOSYALARI)
    def test_dogru_20C_sayisi_ipucunda_var(self, goreli):
        """Her ipucu satırı 20 °C doymuş sıvı sayısını KENDİSİ taşımalı."""
        for satir in self._ipucu_satirlari(goreli):
            assert '785' in satir, (
                f'{goreli}: bir yoğunluk ipucu satırı 20 °C doymuş sıvı '
                'N₂O yoğunluğunu (785 kg/m³) yazmıyor.')

    def test_urun_zinciri_1220_uretmiyor(self):
        """Tek kaynak, hiçbir referans sıcaklıkta 1220'ye yakın dönemez."""
        from hrma.data.external_data_fetcher import (
            oxidizer_reference_density)
        for T in (273.15, 293.15, 298.15, 303.15):
            rho = oxidizer_reference_density('n2o', temperature=T)['density']
            assert rho < 1100.0, (
                f'{T} K: tek kaynak {rho:.1f} kg/m³ döndü — NBP değeri '
                'depolama yoğunluğu diye sızıyor.')

    def test_olu_density_liquid_alani_sayi_tasimiyor(self):
        """Tüketicisi olmayan alan YANLIŞ sayı öğretemez (kardeş desen).

        ``external_data_fetcher._initialize_backup_data`` aynı kusuru Z1'de
        ``None`` + "TÜKETİLMİYOR" künyesiyle kapattı; bu sözlük de aynı
        deseni izler.
        """
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        ca = CombustionAnalyzer.__new__(CombustionAnalyzer)
        # __init__ ağırdır; yalnız sözlük tanımını okuyoruz.
        kaynak = _oku('engines/combustion_analysis.py')
        for satir in kaynak.splitlines():
            if "'density_liquid'" not in satir:
                continue
            assert 'None' in satir, (
                f'Ölü yoğunluk alanına sayı geri gelmiş: {satir.strip()}')
        assert ca is not None


# ---------------------------------------------------------------------------
# P12aB2-01 — enjektör ΔP: ekran metni ⟷ çözücü birimi
# ---------------------------------------------------------------------------
class TestP12aB201EnjektorDeltaPBirimi:
    """İpucu ΔP'yi "oda basıncının yüzdesi" diye öğretemez.

    Çözücü alanı MUTLAK BAR okur (``_override_val('injector_pressure_drop',
    0.2, 200.0)``). Ekran "% of Pc" öğrettiği sürece Pc = 200 barda
    kullanıcının girdiği 20, ÖĞRETİLENİN yarısı kadar bir ΔP/Pc üretir
    (0,10 ⟷ 0,20) ve chug hükmü ters döner.

    ÖK-10 gereği onarım TEK ETİKET değiştirmez: metin İKİ KİPİ (boş alan ->
    otomatik %20 · dolu alan -> mutlak bar) ayrı ayrı söylemek zorundadır.
    """

    ANAHTAR = 'liq.ui.pressure_drop_across_injector_as_percentage'
    DOSYALAR = ('templates/liquid.html', 'static/js/i18n_pages.js')

    def _ipucu_satirlari(self, goreli):
        return [s for s in _oku(goreli).splitlines() if self.ANAHTAR in s]

    @pytest.mark.parametrize('goreli', DOSYALAR)
    def test_yuzde_ogretisi_kalmadi(self, goreli):
        for satir in self._ipucu_satirlari(goreli):
            dusuk = satir.lower()
            assert 'drop across injector as percentage' not in dusuk, (
                f'{goreli}: ipucu ΔP\'yi hâlâ yüzde diye öğretiyor.')
            assert 'basınç düşümünün oda basıncına oranı' not in dusuk, (
                f'{goreli}: TR ipucu ΔP\'yi hâlâ oran diye öğretiyor.')

    @pytest.mark.parametrize('goreli', DOSYALAR)
    def test_iki_kip_de_yaziyor(self, goreli):
        """ÖK-10: otomatik kip ve kullanıcı kipi AYRI AYRI anlatılmalı.

        V301/L-D (SV-16) — BEKLENTİ DEĞİŞTİ: künyeler hibrit enjektör
        aracınınkiydi ('auto (20% of Pc)' / 'user override'); SIVI yanıtı bu
        iki metni HİÇ basmıyor (ölçüldü: kati-sivi/L-D/onceson_sonra.json'da
        0 geçiş; A-sivi SV-16 bulgusunun kendisi). Kip künyeleri sıvı
        çözücünün tek tanımından (``injection_system.pressure_drop_source``)
        okunur; iddia (iki kip ayrı ayrı anlatılır) aynen duruyor.
        """
        from hrma.engines.liquid_rocket_engine import (
            INJECTOR_DP_SOURCE_TYPE_RATIO as DP_SOURCE_AUTO,
            INJECTOR_DP_SOURCE_USER as DP_SOURCE_USER)
        satirlar = self._ipucu_satirlari(goreli)
        assert satirlar, f'{goreli}: ipucu anahtarı kaybolmuş.'
        for satir in satirlar:
            assert DP_SOURCE_AUTO in satir, (
                f'{goreli}: otomatik kip künyesi ({DP_SOURCE_AUTO!r}) '
                'ipucunda yazmıyor.')
            assert DP_SOURCE_USER in satir, (
                f'{goreli}: kullanıcı kipi künyesi ({DP_SOURCE_USER!r}) '
                'ipucunda yazmıyor.')

    @pytest.mark.parametrize('goreli', DOSYALAR)
    def test_ipucu_cozucunun_bandini_soyluyor(self, goreli):
        """Metindeki kabul bandı, çözücünün GERÇEK bandı olmalı."""
        # V301/L-A (SV-01): bant artık çözücünün TEK tablosundadır
        # (``LIQUID_INPUT_BANDS``; motor ve uç kapısı aynı satırı okur).
        # Kaynak metnini regex'le taramak yerine tablonun kendisi okunur.
        from hrma.engines.liquid_rocket_engine import LIQUID_INPUT_BANDS
        alt, ust = LIQUID_INPUT_BANDS['injector_pressure_drop'][:2]
        # TR metni ondalık AYIRACI virgüldür (0,2); iki yazım da kabul.
        alt_yazimlar = (f'{alt:g}', f'{alt:g}'.replace('.', ','))
        for satir in self._ipucu_satirlari(goreli):
            assert any(y in satir for y in alt_yazimlar), (
                f'{goreli}: ipucu alt sınırı ({alt:g} bar) yazmıyor.')
            assert f'{ust:g}' in satir, (
                f'{goreli}: ipucu üst sınırı ({ust:g} bar) yazmıyor.')

    @pytest.mark.parametrize('goreli', DOSYALAR)
    def test_ipucu_ham_HTML_varligi_tasimiyor(self, goreli):
        """i18n metni ``textContent`` ile basılır; ``&quot;`` ham görünür."""
        for satir in self._ipucu_satirlari(goreli):
            assert '&quot;' not in satir, (
                f'{goreli}: ipucunda ham HTML varlığı var.')

    def test_cozucu_alani_MUTLAK_bar_okumaya_devam_ediyor(self, client):
        """Ekran metni düzeldi diye çözücü kipi değişmemeli (kapsam kontrolü)."""
        r = client.post('/calculate_liquid', json=_sivi_yuk(
            chamber_pressure=200.0, injector_pressure_drop=20.0))
        assert r.status_code == 200
        inj = r.get_json()['injector_design']
        # Pc = 200 bar: metin yüzde öğretseydi 20 -> 40 bar beklenirdi.
        # Çözücü MUTLAK okur, yani 20 bar (ΔP/Pc = 0,10).
        for alan in ('injection_pressure_drop_fuel_bar',
                     'injection_pressure_drop_ox_bar'):
            assert inj[alan] == pytest.approx(20.0, rel=1e-9), (
                f'{alan} = {inj[alan]}: alan artık yüzde gibi okunuyor — '
                'kip sessizce değişmiş.')
