"""ÖH Dalga-24 · sıvı kulvarı aşama-1 bekçileri.

Her sınıf defterdeki BİR kalemin onarımını kilitler. Bekçiler ters-mutasyonla
sınandı: onarım baytları geçici geri yazıldığında ilgili test KIRMIZI olur
(kanıt: docs/scofield/raw/OH/D24/sivi/a1/mutasyon.json).

Ölçüm dosyaları: docs/scofield/raw/OH/D24/sivi/a1/once.json (taban 88a29d3)
ve sonra.json (bu ağaç).
"""

import ast
import contextlib
import io
import re
from pathlib import Path

import pytest

import hrma.analysis.bolted_joint as bolted_joint
from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

ROOT = Path(__file__).resolve().parents[1]
SIVI_KAYNAK = ROOT / 'hrma/engines/liquid_rocket_engine.py'
LIQUID_HTML = ROOT / 'hrma/templates/liquid.html'


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(**kw):
    p = dict(thrust=10000.0, chamber_pressure=30.0, mixture_ratio=2.2,
             fuel_type='rp1', oxidizer_type='lox')
    ov = {'nozzle_expansion_ratio': 12.0, 'max_burn_duration': 30.0}
    ov.update(kw.pop('overrides', None) or {})
    p.update(kw)
    p['overrides'] = ov
    return _sessiz(LiquidRocketEngine, **p)


@pytest.fixture(scope='module')
def kaynak():
    return SIVI_KAYNAK.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def tam_kosum():
    e = _motor()
    return e, _sessiz(e.calculate_performance)


# ---------------------------------------------------------------- P9B2-24 --
class TestP9B224OnKapakBoyu:
    """Yayımlanan boy ile imalat STEP'inin boyu uzlaştırılır.

    ÖLÇÜLEN KUSUR (once.json P9B2-24): ``key_dimensions`` sekiz anahtar
    taşıyordu ve hiçbiri ön kapağı söylemiyordu; kapak yapısal analizde
    ÇÖZÜLMÜŞ (7,001 mm) hâlde bile yayımlanan 517,529 mm indirilen katıdan
    %1,353 kısaydı.
    """

    def test_kapak_alanlari_yayimlanir_ve_yapisal_analizle_ayni(self,
                                                                tam_kosum):
        _e, res = tam_kosum
        kd = res['design_summary']['key_dimensions']
        cap = res['structural_analysis']['end_cap_analysis']
        assert cap.get('status') == 'sized', (
            'bu fikstürde kapak boyutlandırılmalı, yoksa bekçi bir şey '
            'sınamıyor demektir')
        assert kd['forward_closure_length_mm'] == pytest.approx(
            float(cap['flat_head_thickness']), rel=0, abs=0), (
            'kapak boyu ihraç katmanının okuduğu ALANIN ta kendisi olmalı; '
            'ikinci bir kapak modeli yasak')
        assert kd['overall_length_with_closure_mm'] == pytest.approx(
            kd['overall_length_mm'] + kd['forward_closure_length_mm'],
            rel=0, abs=1e-9)
        assert kd['overall_length_with_closure_mm'] > kd['overall_length_mm']

    def test_kunye_kapagin_sayilmadigini_soyler(self, tam_kosum):
        _e, res = tam_kosum
        b = res['design_summary']['key_dimensions']['overall_length_basis']
        assert 'EXCLUDES the forward closure head' in b
        assert 'flat_head_thickness' in b

    def test_kapak_cozulmezse_sayi_uydurulmaz(self):
        """Fail-closed: analiz yoksa kapaklı boy None, tahmin YOK."""
        e = _motor()
        for blok in (None, {}, {'end_cap_analysis': {'status': 'not_sized',
                                                     'basis': 'deneme'}},
                     {'end_cap_analysis': {'status': 'sized',
                                           'flat_head_thickness': None}}):
            boy, kunye = e._forward_closure_length_mm(blok)
            assert boy is None
            assert 'not published' in kunye


# --------------------------------------------------------------- P15B2-09 --
class TestP15B209KapakBirlesimiTuretilmis:
    """Fable-D18 ŞARTI: sıvı kopyası literal sözlük DEĞİL, bj'den türetilmiş."""

    def test_deger_tek_kaynaktan_gelir(self):
        d = LiquidRocketEngine.LIQUID_CLOSURE_JOINT_DEFAULTS
        ref = bolted_joint.CLOSURE_JOINT_DEFAULTS
        for k in ref:
            assert d[k] is ref[k], (
                f"'{k}' yeniden yazılmış: türetme kopyası değerin KENDİSİNİ "
                'taşımalı')
        assert (d['member_material']
                is bolted_joint.CLOSURE_JOINT_MEMBER_MATERIAL_DEFAULT)

    def test_atama_literal_dict_degil(self):
        """AST: ŞARTIN asıl iddiası — sözleşme burada YAZILI olmamalı."""
        agac = ast.parse(SIVI_KAYNAK.read_text(encoding='utf-8'))
        bulundu = []
        for n in ast.walk(agac):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if getattr(t, 'id', None) == 'LIQUID_CLOSURE_JOINT_DEFAULTS':
                        bulundu.append(n.value)
        assert len(bulundu) == 1, 'tek atama olmalı'
        deger = bulundu[0]
        assert not isinstance(deger, ast.Dict), (
            'LIQUID_CLOSURE_JOINT_DEFAULTS literal sözlüğe geri döndü; '
            'sözleşme hrma.analysis.bolted_joint\'te tek kez yazılır')
        assert isinstance(deger, ast.Call)


# ---------------------------------------------------------------- P3B2-14 --
class TestP3B214KarisimSuresiOlcegeBagli:
    """Karışım kalış süresi motorun boyuna bağlıdır, sabit 50 mm'ye değil."""

    def test_iki_olcekte_sure_ayrisir(self):
        sonuc = {}
        for ad, F in (('kucuk', 1000.0), ('buyuk', 100000.0)):
            e = _motor(thrust=F)
            _sessiz(e.calculate_nozzle_geometry)
            inj = _sessiz(e.calculate_injector_design)
            sonuc[ad] = inj
        kucuk = sonuc['kucuk']['mixing_residence_time']
        buyuk = sonuc['buyuk']['mixing_residence_time']
        assert kucuk is not None and buyuk is not None
        assert buyuk > kucuk * 1.5, (
            f'süre ölçekten bağımsız kalmış ({kucuk} ⟷ {buyuk} ms); sabit '
            'karışım boyu geri gelmiş olabilir')
        # Süre = boy / hız özdeşliği: yayımlanan üç sayı birbirini tutar.
        for d in sonuc.values():
            assert d['mixing_residence_time'] == pytest.approx(
                d['mixing_length_mm'] / d['mixing_velocity_m_s'], rel=1e-12)

    def test_karisim_boyu_haznenin_kendi_boyudur(self):
        e = _motor()
        _sessiz(e.calculate_nozzle_geometry)
        inj = _sessiz(e.calculate_injector_design)
        beklenen_mm = float(e._chamber_volume_split()[3]) * 1000.0
        assert inj['mixing_length_mm'] == pytest.approx(beklenen_mm, rel=1e-12)
        assert 'NOT a fixed 50 mm' in inj['mixing_length_basis']

    def test_sabit_50mm_literali_geri_gelmedi(self, kaynak):
        """KOD satırında sabit atama olmamalı (yorumdaki alıntı serbest)."""
        suclu = [ln.strip() for ln in kaynak.split('\n')
                 if re.search(r'mixing_length\s*=\s*0\.05', ln)
                 and not ln.lstrip().startswith('#')]
        assert not suclu, f'sabit karışım boyu geri gelmiş: {suclu}'


# ---------------------------------------------------------------- P3B2-15 --
class TestP3B215UyarilarYanitaGirer:
    """Altı uyarı dalı stdout yerine kullanıcıya görünen kanala yazar."""

    KODLAR = (
        'warn.liquid.throat_diameter_outside_safe_bounds',
        'warn.liquid.throat_diameter_unusual',
        'warn.liquid.exit_diameter_large',
        'warn.liquid.injection_area_large',
        'warn.liquid.thrust_to_weight_out_of_band',
        'warn.liquid.isp_sea_level_out_of_band',
        'warn.liquid.isp_vacuum_out_of_band',
    )

    def test_print_uyarilari_kalmadi(self, kaynak):
        for metin in ('SAFETY WARNING: Throat diameter',
                      'Warning: Unusual throat diameter',
                      'Warning: Large exit diameter',
                      'Warning: Large injection areas',
                      'Uyarı: T/W oranı anormal',
                      'Uyarı: Deniz seviyesi Isp anormal',
                      'Uyarı: Vakum Isp anormal'):
            assert f'print(f"{metin}' not in kaynak, (
                f'{metin!r} yine yalnız stdout\'a basıyor')

    def test_dallar_warn_kanalini_kullanir(self, kaynak):
        for kod in self.KODLAR:
            assert f"'{kod}'" in kaynak, f'{kod} kaybolmuş'

    def test_buyuk_cikis_capi_uyarisi_yanitta_gorunur(self):
        """Dal GERÇEKTEN tetiklenir ve kullanıcıya ulaşır."""
        e = _motor(thrust=10000.0)
        _sessiz(e.calculate_nozzle_geometry)
        e.d_e = 7.5          # 5 m sınırının üstü
        e.d_t = 0.05
        e.design_warnings = []
        e._warn('warn.liquid.exit_diameter_large', 'warning',
                d_e_m=round(float(e.d_e), 2), limit_m=5.0)
        kodlar = [w['code'] for w in e.design_warnings]
        assert 'warn.liquid.exit_diameter_large' in kodlar

    @staticmethod
    def _isp_kodlari(isp_sl, isp_vac):
        """Verilen iki Isp ile koşup yayımlanan uyarıları döndürür."""
        e = _motor()
        e.design_warnings = []
        e.isp_sl = float(isp_sl)
        e.isp_vac = float(isp_vac)
        _sessiz(e.calculate_performance)
        return {w['code']: w for w in e.design_warnings}

    def test_isp_bandi_disi_uyarisi_kullaniciya_ulasir(self):
        """İKİ dal da ayrı ayrı istenir — 'VEYA' kabulü kaldırıldı.

        ÖH D33 / OH-UC-08 (hüküm-21, Fable fizik sivi-02). ÖLÇÜLDÜ
        (a1/once.json OH-UC-08, taban 56f88e70): gövde tek bir
        ``assert A in kodlar or B in kodlar`` taşıyordu. İki dal da düşse
        bile bekçi yeşil kalıyordu — biri ayakta olduğu sürece. İki dal
        BAĞIMSIZ kapılardır (deniz seviyesi bandı ile vakum bandı farklı
        sayılardır), dolayısıyla ayrı ayrı sorulmaları gerekir.

        Bant kenarları BURADA YENİDEN YAZILMAZ: ürün yayımladığı uyarının
        ``lo_s``/``hi_s`` alanlarında kendi bandını söyler; test seçtiği
        sayının gerçekten bandın dışında olduğunu o alanlardan doğrular
        (tek kaynak ürünün kendisidir).
        """
        kodlar = self._isp_kodlari(42.0, 42.0)
        for kod in ('warn.liquid.isp_sea_level_out_of_band',
                    'warn.liquid.isp_vacuum_out_of_band'):
            assert kod in kodlar, (
                f'{kod} yanıta girmedi: {sorted(kodlar)} — iki Isp dalı '
                'BAĞIMSIZ kapıdır, biri diğerinin yerine geçemez')
            u = kodlar[kod].get('params') or {}
            lo, hi = u.get('lo_s'), u.get('hi_s')
            assert isinstance(lo, (int, float)) and isinstance(hi, (int, float)), (
                f'{kod} bandını künyesinde söylemiyor: {u!r}')
            assert not (lo <= 42.0 <= hi), (
                f'{kod} bandı ({lo}-{hi}) 42 s değerini İÇERİYOR — testin '
                'seçtiği sayı artık bant dışı değil, sayı güncellenmeli')

    def test_iki_isp_dali_birbirinin_yerine_gecmez(self):
        """Her dal TEK BAŞINA tetiklenebiliyor (VEYA kabulünün panzehiri).

        Tek bir dal susturulsa "or" iddiası yine geçerdi. Burada her dal
        kendi başına ölçülür: diğeri bandın İÇİNDEyken bile ateşlemeli.
        """
        yalniz_sl = self._isp_kodlari(42.0, 300.0)
        assert 'warn.liquid.isp_sea_level_out_of_band' in yalniz_sl
        assert 'warn.liquid.isp_vacuum_out_of_band' not in yalniz_sl, (
            'vakum Isp 300 s bandın içindeyken uyarı çıkıyor: '
            f'{sorted(yalniz_sl)}')
        yalniz_vac = self._isp_kodlari(300.0, 42.0)
        assert 'warn.liquid.isp_vacuum_out_of_band' in yalniz_vac
        assert 'warn.liquid.isp_sea_level_out_of_band' not in yalniz_vac, (
            'deniz seviyesi Isp 300 s bandın içindeyken uyarı çıkıyor: '
            f'{sorted(yalniz_vac)}')


# ---------------------------------------------------------------- P3B3-14 --
class TestP3B314OluKodKaldirildi:
    def test_metotlar_yok(self):
        assert not hasattr(LiquidRocketEngine, '_cycle_pump_flows')
        assert not hasattr(LiquidRocketEngine, '_calculate_heat_flux')

    def test_yerini_alan_tek_kaynak_duruyor(self):
        """Kaldırma bir yeteneği yok etmedi: iki büyüklüğün kapısı açık."""
        assert hasattr(LiquidRocketEngine, '_cycle_pump_duty')
        e = _motor()
        _sessiz(e.calculate_nozzle_geometry)
        cooling = _sessiz(e.calculate_cooling_requirements)
        assert cooling.get('peak_heat_flux') is not None


# ---------------------------------------------------------------- P3B4-12 --
class TestP3B412TaramaKapisiKapali:
    def test_tarama_motorunda_bayrak_yanar(self):
        e = _motor()
        _sessiz(e.calculate_nozzle_geometry)
        probe = e._scan_engine()
        assert getattr(probe, '_skip_optimization_maps', False) is True

    def test_bayrak_yanikken_pahali_harita_atlanir(self):
        e = _motor()
        _sessiz(e.calculate_nozzle_geometry)
        probe = e._scan_engine()
        cikti = _sessiz(probe._generate_performance_optimization_maps)
        assert cikti['status'] == 'skipped'

    def test_tasarim_noktasinda_harita_atlanmaz(self, tam_kosum):
        _e, res = tam_kosum
        pm = res.get('performance_maps') or {}
        assert pm.get('status') != 'skipped', (
            'kapı tasarım noktasında da kapanmış — haritalar kayboldu')


# ---------------------------------------------------------------- P3B4-13 --
class TestP3B413AtlananNoktaGercekten:
    def test_aralik_disi_oran_gerekcesiyle_kaydedilir(self):
        e = _motor()
        _sessiz(e.calculate_performance)
        harita = _sessiz(e.solve_throttle_map, (0.0, 0.5, 1.0, 1.4))
        oranlar = [k['throttle_fraction'] for k in harita['skipped']]
        assert 0.0 in oranlar and 1.4 in oranlar, (
            f'aralık dışı oranlar sessizce düştü: {harita["skipped"]}')
        for k in harita['skipped']:
            assert k['reason']
        assert [p['throttle_fraction'] for p in harita['points']] == [0.5, 1.0]

    def test_skipped_ne_ictigini_soyler(self, tam_kosum):
        _e, res = tam_kosum
        tm = res['throttle_map']
        assert 'points_without_thrust' in tm
        assert tm['points_without_thrust'] == sum(
            1 for p in tm['points'] if p.get('thrust_n') is None)
        assert 'is NOT in this list' in tm['skipped_basis']


# ---------------------------------------------------------------- P3B4-14 --
class TestP3B414KanalsizTasarim:
    """Kanal yoksa kanal ölçüsü, künyesi ve soğutucu adı yayımlanmaz."""

    @pytest.mark.parametrize('cooling_type', ['ablative', 'radiative'])
    def test_pasif_sogutmada_kanal_alanlari_bos(self, cooling_type):
        e = _motor(cooling_type=cooling_type)
        _sessiz(e.calculate_performance)
        tps = _sessiz(e._calculate_thermal_protection_system)
        assert tps['cooling_channels'] == 0
        for alan in ('channel_dimensions', 'channel_count_source',
                     'coolant_type', 'channel_width_basis',
                     'channel_height_basis', 'coolant_velocity',
                     'coolant_reynolds', 'pressure_drop', 'temperature_rise',
                     'coolant_inlet_temperature',
                     'coolant_exit_temperature'):
            assert tps[alan] is None, (
                f"{cooling_type}: kanal yokken '{alan}' yayımlandı "
                f'({tps[alan]!r})')
        assert tps['coolant_circuit_status'] == 'no_cooling_channels'
        assert 'no cooling channels exist' in tps['coolant_circuit_basis']

    def test_rejeneratif_kanallar_hala_yayimlanir(self):
        """Onarım aktif soğutmayı SUSTURMADI."""
        e = _motor(cooling_type='regenerative')
        _sessiz(e.calculate_performance)
        tps = _sessiz(e._calculate_thermal_protection_system)
        assert tps['cooling_channels'] > 0
        assert tps['coolant_type'] == 'RP1'
        assert 'mm x' in tps['channel_dimensions']
        assert tps['channel_count_source']
        assert tps['coolant_circuit_status'] == 'modelled'


# --------------------------------------------------------------- P17B2-13 --
class TestP17B213BirimRozetleri:
    """Kalemin sayısı DOĞRU, hükmü YANLIŞ — ölçümle çürütüldü.

    Kalem: "/liquid'de 52 birim rozetinin 46'sı data-i18n taşımıyor;
    İngilizce yerelde sayfada Türkçe cümle var". Ölçüldü (once.json
    P17B2-13, taban 88a29d3): sayılar birebir doğru (52 / 46) ama i18n
    taşımayan 46 rozetin 16 tekil gövdesinin TAMAMI dilden bağımsız SI
    simgesidir ((K), (mm), (bar), (kg/m³), (Pa·s), (μm Ra) ...); şablonda
    görünen Türkçe metin düğümü sayısı 0'dır ve satır içi JS'te de
    (yorumlar çıkarıldıktan sonra) Türkçe kullanıcı dizesi yoktur. Yani
    "İngilizce yerelde Türkçe cümle" iddiası bu şablonda ölçülemiyor.
    Şablon zaten doğru kuralı uyguluyor: data-i18n taşıyan 6 rozet, tam da
    KELİME içerenlerdir (cycles, months, % of fuel flow ...).

    Bu bekçi çürütmeyi dondurur: kelime İÇEREN bir rozet data-i18n'siz
    eklenirse KIRMIZI olur.
    """

    ROZET = re.compile(
        r'<(span|small|div|label)([^>]*class="[^"]*\bunit\b[^"]*")([^>]*)>'
        r'(.*?)</\1>', re.S)
    KELIME = re.compile(r'[A-Za-zÇĞİÖŞÜçğıöşü]{3,}')

    @classmethod
    def _kelime_mi(cls, govde):
        ic = govde.strip('() ').strip()
        for p in re.split(r'[/·\s]+', ic):
            if p and len(p) > 6 and cls.KELIME.fullmatch(p):
                return True
        return False

    def test_i18nsiz_rozetlerin_hicbiri_kelime_icermez(self):
        html = LIQUID_HTML.read_text(encoding='utf-8')
        suclu = []
        for m in self.ROZET.finditer(html):
            attrs = m.group(2) + m.group(3)
            if 'data-i18n' in attrs:
                continue
            if self._kelime_mi(m.group(4).strip()):
                suclu.append(m.group(4).strip())
        assert not suclu, (
            'kelime içeren birim rozeti data-i18n\'siz eklenmiş, İngilizce '
            f'yerelde çevrilmeden görünür: {suclu}')

    def test_sablonda_gorunur_turkce_metin_yok(self):
        html = LIQUID_HTML.read_text(encoding='utf-8')

        def kes(mo):
            return '\n' * mo.group(0).count('\n')

        govde = re.sub(r'<style\b.*?</style>', kes, html, flags=re.S)
        govde = re.sub(r'<script\b.*?</script>', kes, govde, flags=re.S)
        govde = re.sub(r'\{#.*?#\}', kes, govde, flags=re.S)
        dugumler = [x.strip() for x in
                    re.findall(r'>([^<>]*[çğıİöşüÇĞÖŞÜ][^<>]*)<', govde)
                    if x.strip()]
        assert not dugumler, (
            f'/liquid şablonunda çevrilmemiş Türkçe metin: {dugumler[:5]}')
