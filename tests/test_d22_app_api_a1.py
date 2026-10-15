"""ÖH D22 / app-api aşama-1 bekçileri.

Her sınıf tek bir defter kalemini KİLİTLER: onarım geri alınırsa kırmızı olur
(ters-mutasyon kanıtı ``docs/scofield/raw/OH/D22/app-api/a1/mutasyon*.json``).

Kalemler: P7B1-05 (port_count bağlanması), P7B1-10 (tek tank sıcaklığı),
P7B1-12 (0 ⟷ "verilmedi"), P16B3-06 (bütçe hükmü yazı-tura),
OH-D20-07 (STL defter tavanı — ÇÜRÜTÜLDÜ, kapanış bekçisi).
"""
import ast
import json
import os

import pytest

from hrma.app import app


HIBRIT = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'chamber_pressure': 20.0, 'fuel_type': 'htpb',
          'oxidizer_type': 'n2o'}

_APP_PY = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'hrma', 'app.py')


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _gonder(istemci, yol, yuk):
    r = istemci.post(yol, json=yuk)
    return r.status_code, (r.get_json() or {})


class TestP7B1_05PortCountBagli:
    """port_count motora GEÇMELİ; geçmezse 4 ve 8 bit-aynı yanıt verir."""

    def test_port_count_uc_hibrit_ucta_motora_geciyor(self):
        """Statik: üç hibrit kurucusu da ``port_count`` argümanını taşır.

        ÖLÇÜLDÜ (taban b84b10a): ``hrma/app.py``de ``port_count`` 0 eşleşme.
        """
        agac = ast.parse(open(_APP_PY, encoding='utf-8').read())
        kuruculu = 0
        for n in ast.walk(agac):
            if (isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name)
                    and n.func.id == 'HybridRocketEngine'):
                if any(kw.arg == 'port_count' for kw in n.keywords):
                    kuruculu += 1
        assert kuruculu >= 3, (
            'port_count en az üç hibrit kurucusuna (/calculate, '
            f'/api/quick-geometry, /api/transient-analysis) geçmeli; {kuruculu} bulundu')

    def test_dort_ve_sekiz_port_ayni_yaniti_vermez(self, istemci):
        d4, y4 = _gonder(istemci, '/calculate', dict(HIBRIT, port_count=4))
        d8, y8 = _gonder(istemci, '/calculate', dict(HIBRIT, port_count=8))
        assert d4 == 200 and d8 == 200, (d4, d8)
        assert json.dumps(y4, sort_keys=True, default=str) != \
            json.dumps(y8, sort_keys=True, default=str), (
                'port_count = 4 ile 8 BİT-AYNI yanıt veriyor: alan motora '
                'bağlı değil (P7B1-05).')

    def test_cok_port_uyarisi_http_uzerinden_dogabiliyor(self, istemci):
        durum, yanit = _gonder(istemci, '/calculate', dict(HIBRIT,
                                                           port_count=4))
        assert durum == 200
        govde = json.dumps(yanit, default=str)
        assert 'warn.hybrid.multi_port_equivalent_model' in govde, (
            'İki dile paketlenmiş çok-port uyarısı HTTP üzerinden hiç '
            'doğamıyor (P7B1-05).')

    def test_port_count_sifir_adiyla_reddedilir(self, istemci):
        """Fail-closed: 0 sessizce 1 olmaz."""
        durum, _y = _gonder(istemci, '/calculate', dict(HIBRIT, port_count=0))
        assert durum != 200, 'port_count = 0 kabul edilmemeli'


class TestP7B1_10TekTankSicakligi:
    """Tek istekte iki tank sıcaklığı çözümü olamaz."""

    #: Tank sıcaklığını FİİLEN tüketen tek besleme kipi. Varsayılan kipte
    #: sayı hiçbir yaprağa dokunmaz (aşağıda ölçüldü), o yüzden bu kalemin
    #: eşitlik iddiası ancak bu kipte anlamlıdır.
    KIP = {'feed_mode': 'blowdown'}
    #: Kabul edilen ve birbirinden AYRIŞAN iki tank sıcaklığı [K]. 250 K
    #: blowdown'da fiziken reddediliyor (tank basıncı 16,3 bar < 20,0 bar
    #: kamara), 280 K ⟷ 293,15 K ise iki ayrı çözüm veriyor.
    T_A, T_B = 280.0, 293.15

    def _gecici_cozum(self, istemci, **ek):
        d, y = _gonder(istemci, '/api/transient-analysis',
                       dict(HIBRIT, simulation_time=1.0, **self.KIP, **ek))
        return d, json.dumps(y.get('transient'), sort_keys=True, default=str)

    def test_oxidizer_temp_takma_adi_iki_bloga_da_gider(self, istemci):
        """``oxidizer_temp`` verilmişse geçici çözücü de onu kullanır.

        ÖLÇÜLDÜ (taban): motor 250,00 K, çözücü 293,15 K — 43,15 K fark,
        HTTP 200, uyarı yok.

        ÖH D33 / P7B1-10 — DENETİM ŞARTI KARŞILANDI (app-api denetçisi,
        15 Eyl). Eski gövde ``feed_mode`` göndermiyordu ve ÖLÇÜLDÜ
        (a1/once.json P7B1-10, taban 56f88e70) ki **varsayılan kipte tank
        sıcaklığı hiçbir yaprağa dokunmuyor**: 250 K ile 293,15 K bit-aynı
        ``transient`` bloğu veriyor. Yani eşitlik iddiası vakumluydu — iki
        takma ad "aynı" çıkıyordu çünkü İKİSİ DE hiçbir şey yapmıyordu.

        Gövde artık (a) sıcaklığı fiilen tüketen ``feed_mode='blowdown'``
        kipinde koşuyor ve (b) kendi DUYARLILIĞINI ayrıca ölçüyor: aynı
        gövdede iki farklı tank sıcaklığı FARKLI sonuç vermezse test kendini
        geçersiz ilan eder.
        """
        d_duyar_a, s_duyar_a = self._gecici_cozum(
            istemci, tank_temperature=self.T_A)
        d_duyar_b, s_duyar_b = self._gecici_cozum(
            istemci, tank_temperature=self.T_B)
        assert d_duyar_a == 200 and d_duyar_b == 200, (d_duyar_a, d_duyar_b)
        assert s_duyar_a != s_duyar_b, (
            f'tank_temperature = {self.T_A} K ile {self.T_B} K BİT-AYNI '
            'geçici çözüm veriyor: bu gövdede sıcaklık hiçbir yaprağa '
            'dokunmuyor, dolayısıyla aşağıdaki eşitlik iddiası hiçbir şey '
            'kanıtlamaz (denetim şartı, P7B1-10).')

        d_ox, s_ox = self._gecici_cozum(istemci, oxidizer_temp=self.T_A)
        d_tank, s_tank = self._gecici_cozum(istemci, tank_temperature=self.T_A)
        assert d_ox == 200 and d_tank == 200, (d_ox, d_tank)
        assert s_ox == s_tank, (
            f'oxidizer_temp = {self.T_A} K ile tank_temperature = {self.T_A} '
            'K aynı geçici çözümü vermeli; vermiyorsa uç sıcaklığı iki ayrı '
            'yerde çözüyor (P7B1-10).')

    def test_takma_ad_reddi_de_tek_kapidan_geciyor(self, istemci):
        """Fail-closed ayağı: takma ad, REDDİ de aynı yerden alır.

        250 K blowdown'da fiziken reddediliyor. İki takma adın da AYNI 4xx
        hükmünü alması, ikisinin de aynı çözüm noktasına ulaştığını
        gösterir — bu, eşitliğin "ikisi de sessizce düştü" ile
        açıklanamayacağının ikinci kanıtıdır.
        """
        d_ox, _ = self._gecici_cozum(istemci, oxidizer_temp=250.0)
        d_tank, _ = self._gecici_cozum(istemci, tank_temperature=250.0)
        assert d_ox == d_tank, (d_ox, d_tank)
        assert d_ox != 200, (
            '250 K blowdown tankı 20 bar kamarayı besleyemez; uç bunu '
            'kabul ediyorsa fail-closed kapısı düşmüş')

    def test_ucta_tek_tank_sicakligi_cozumu_var(self):
        """Statik: uç sıcaklığı TEK yerde çözer — VARLIK ölçülür.

        ÖH D33 / P7B1-10 — DENETİM ŞARTI. Eski ayak yalnız eski dizenin
        YOKLUĞUNU soruyordu (``... not in kaynak``); o dize bir gün elle
        yeniden biçimlendirilse (satır kaydırma, tırnak değişimi) bekçi
        kusur geri gelmişken de yeşil kalırdı. Ayak artık takma-ad
        YÜKSELTMESİNİN VARLIĞINI AST ile ölçer:

        1. ``/api/transient-analysis`` gövdesinde ``_tank_T_govde``
           değişkenine atama var (tek çözüm noktası);
        2. o gövdedeki HİÇBİR çağrı ``tank_temperature=`` anahtarına
           ``data``dan okuyan bir ifade vermiyor — hepsi çözülmüş tek
           değişkeni taşıyor.
        """
        agac = ast.parse(open(_APP_PY, encoding='utf-8').read())
        govde = None
        for n in ast.walk(agac):
            if not isinstance(n, ast.FunctionDef):
                continue
            for dec in n.decorator_list:
                if (isinstance(dec, ast.Call)
                        and getattr(dec.func, 'attr', None) == 'route'
                        and dec.args
                        and isinstance(dec.args[0], ast.Constant)
                        and dec.args[0].value == '/api/transient-analysis'):
                    govde = n
        assert govde is not None, '/api/transient-analysis ucu bulunamadı'

        atamalar = {t.id for d in ast.walk(govde)
                    if isinstance(d, ast.Assign)
                    for t in d.targets if isinstance(t, ast.Name)}
        assert '_tank_T_govde' in atamalar, (
            'takma-ad yükseltmesi (_tank_T_govde) uçtan kalkmış: sıcaklık '
            'yine iki yerde çözülüyor olabilir (P7B1-10).')

        suclu = []
        for d in ast.walk(govde):
            if not isinstance(d, ast.Call):
                continue
            for kw in d.keywords:
                if kw.arg != 'tank_temperature':
                    continue
                if isinstance(kw.value, ast.Name):
                    continue            # çözülmüş tek değişken — meşru
                if 'data' in {getattr(x, 'id', None) for x in ast.walk(kw.value)}:
                    suclu.append(ast.dump(kw.value)[:120])
        assert not suclu, (
            'Motor kurucusu tank sıcaklığını istekten YENİDEN çözüyor '
            f'(P7B1-10): {suclu}')


class TestP7B1_12SifirVerilmedigDegildir:
    """``mdot_ox = 0`` motor sonucuyla doldurulamaz."""

    SPEC = {'motor_type': 'hybrid', 'injector_type': 'showerhead',
            'rho_ox': 785.0, 'Pc_bar': 20.0, 'dp_bar': 5.0,
            'fluid_ox': 'n2o', 'T_ox_K': 293.15}
    MOTOR_SONUCU = {'mdot_ox': 99.0, 'mdot_fuel': 16.5, 'Pc_bar': 20.0,
                    'T_c_K': 3000.0, 'mw_gas': 25.0}

    def _cagir(self, istemci, ek):
        return _gonder(istemci, '/api/injector-design',
                       dict(self.SPEC, from_results=True,
                            motor_results=self.MOTOR_SONUCU, **ek))

    def test_sifir_gonderen_istek_motor_sonucuyla_cozulmez(self, istemci):
        d0, y0 = self._cagir(istemci, {'mdot_ox': 0})
        assert d0 != 200, (
            'mdot_ox = 0 gönderen istek 200 aldı: 0 "verilmedi" sayılıp '
            'motor sonucundaki 99,0 kg/s ile çözüldü (P7B1-12).')

    def test_sifir_ile_hic_gondermemek_ayni_yanit_degildir(self, istemci):
        d0, y0 = self._cagir(istemci, {'mdot_ox': 0})
        dy, yy = self._cagir(istemci, {})
        assert (d0, json.dumps(y0, sort_keys=True, default=str)) != \
            (dy, json.dumps(yy, sort_keys=True, default=str)), (
                '0 ile "gönderilmedi" bit-aynı yanıt veriyor (P7B1-12).')

    def test_gercek_deger_hala_calisiyor(self, istemci):
        d, y = self._cagir(istemci, {'mdot_ox': 5.0})
        assert d == 200, (d, y.get('error'))
        assert y['design']['ox_circuit']['mdot_kg_s'] == pytest.approx(5.0)

    def test_hic_gonderilmeyen_alan_hala_dolduruluyor(self, istemci):
        d, y = self._cagir(istemci, {})
        assert d == 200, (d, y.get('error'))
        assert y['design']['ox_circuit']['mdot_kg_s'] == pytest.approx(99.0)


class TestP16B3_06ButceHukmuKararli:
    """Aynı gövde her koşuda aynı durum kodunu almalı."""

    # ÖH D28 a1 / OH-D27-03: ``param_type`` EKLENDİ. Bu yük eskiden
    # ``sweep_parameter`` yazıyordu — uç o adı OKUMUYOR, dolayısıyla
    # süpürme ekseni ucun kendi sessiz ``'of_ratio'`` yedeğinden
    # geliyordu. Yedek fail-closed hâle geldiği için yük artık ekseni
    # ADIYLA söyler. Bekçinin KONUSU değişmedi (zaman bütçesi hükmü);
    # ``sweep_parameter`` anahtarı, okunmayan adın hâlâ sessizce
    # düşürüldüğünü göstermek için BİLEREK bırakıldı.
    TABAN = {'sweep_parameter': 'of_ratio', 'param_type': 'of_ratio',
             'param_start': 4.0,
             'param_end': 8.0, 'thrust': 1000, 'burn_time': 10,
             'chamber_pressure': 20.0, 'fuel_type': 'htpb',
             'oxidizer_type': 'n2o'}

    @pytest.fixture(scope='class')
    def nokta_maliyeti(self, istemci):
        """Bu makinede bir noktanın ÖLÇÜLEN maliyeti [s].

        İKİ tarama koşulur ve İKİNCİSİ kullanılır: ilk tarama Cantera
        dengesini ve şablon önbelleklerini ısıtır, o yüzden soğuk ölçüm
        gerçek maliyetin katı çıkar (ölçüldü: soğuk 4,46 s ⟷ ılık ~0,5 s).
        Bekçinin bütçesi bu ölçüden türetildiği için ılık sayı gerekir.
        """
        for _ in range(2):
            d, y = _gonder(istemci, '/parametric-analysis',
                           dict(self.TABAN, param_steps=2,
                                time_budget_s=300.0))
            assert d == 200, (d, y.get('error'))
            assert y['points_succeeded'] >= 1
        return max(y['sweep_wall_time_s'] / y['points_succeeded'], 1e-6)

    def test_makine_hizi_hukmu_degistirmez(self, istemci, nokta_maliyeti):
        """Bütçe en az iki noktayı fonluyorsa yanıt 200 olmalı.

        Eski kural ``nokta_maliyeti * adim > butce`` idi ve BİREBİR AYNI
        gövde arka arkaya 422/200/200/200 alıyordu (once.json P16B3-06).
        Buradaki bütçe üç noktayı fonluyor ama 20 noktayı fonlamıyor:
        eski kuralda 422, yeni kuralda 200 (kesilme BEYAN edilir).
        """
        butce = nokta_maliyeti * 4.0
        d, y = _gonder(istemci, '/parametric-analysis',
                       dict(self.TABAN, param_steps=20,
                            time_budget_s=round(butce, 3)))
        assert d == 200, (
            f'Bütçe ({butce:.2f} s) en az iki noktayı fonluyor ama uç '
            f'422 verdi: hüküm isteğe değil makine hızına bağlı '
            f'(P16B3-06). {y.get("error")}')
        # Kesilme AYRICA eski kuralın 422 vereceğini kanıtlar: tarama
        # bütçeye sığmadı, yani ``nokta_maliyeti * 20 > bütçe``.
        assert 'truncated_by_time_budget' in y, (
            'Kesilen tarama TAM tarama gibi yayımlanamaz — kesilme '
            'ADIYLA beyan edilmeli (ve bu bekçinin ayırt ediciliği '
            'kesilmenin gerçekleşmesine dayanır).')
        assert y['points_succeeded'] >= 2, y['points_succeeded']

    def test_butce_en_kucuk_taramayi_fonlamiyorsa_adiyla_reddedilir(
            self, istemci):
        """Fail-closed: iki nokta bile sığmıyorsa hüküm YAYIMLANMAZ."""
        # Mutlak, makineden bağımsız bütçe: tam bir motor çözümü hiçbir
        # makinede 10 ms'nin altında bitmez, dolayısıyla iki nokta ASLA
        # sığmaz. (``nokta_maliyeti`` ölçüsüne bağlanmaz: ölçü ısınmayla
        # değişir, hükmün ölçütü değişmemeli.)
        d, y = _gonder(istemci, '/parametric-analysis',
                       dict(self.TABAN, param_steps=20,
                            time_budget_s=0.01))
        assert d == 422, (d, y)
        assert y['error'] == 'parametric_time_budget_exceeded'
        assert y['minimum_points'] >= 2
        assert 'results' not in y, 'Reddedilen tarama sonuç yayımlamaz.'

    def test_en_kucuk_adim_tek_kaynaktan_okunur(self):
        """``2`` iki kapıda da elle yazılmaz (ÖK/tek kaynak)."""
        from hrma.app import PARAMETRIC_MIN_STEPS
        kaynak = open(_APP_PY, encoding='utf-8').read()
        assert PARAMETRIC_MIN_STEPS == 2
        assert 'if not (2 <= sweep_points' not in kaynak, (
            'Adım alt sınırı elle yazılmış; PARAMETRIC_MIN_STEPS okunmalı.')


class TestOHD20_07StlDefterTavani:
    """ÇÜRÜTÜLDÜ (D22): sayı sınırıyla düşen jeton 410 veriyor.

    Kalem başlığı ("257. kayıttan sonra ilk jeton 404 'File not found'")
    bu ağaçta ölçümle çürütüldü; bekçi kapanışı KİLİTLER.
    """

    def test_defter_tavaniyla_dusen_jeton_410_verir(self, istemci, tmp_path):
        import hrma.app as A
        ilk = None
        for i in range(A._STL_REGISTRY_MAX + 1):
            p = tmp_path / f'm{i}.stl'
            p.write_text('solid x\nendsolid x\n')
            jeton = A._register_stl_download(str(p))
            if ilk is None:
                ilk = jeton
        r = istemci.get(f'/download/stl/{ilk}')
        assert r.status_code == 410, (
            f'Sayı sınırıyla düşen jeton {r.status_code} verdi; ikame '
            'doktrini 410 ister (OH-D20-07).')
        govde = r.get_json() or {}
        assert govde.get('error') == 'stl_download_window_expired'
        assert ilk in A._STL_EXPIRED_TOKENS
        assert A._STL_EXPIRED_TOKENS[ilk] == A._STL_DUSME_DEFTER_TAVANI
