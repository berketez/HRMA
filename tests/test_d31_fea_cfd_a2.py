# tests/ — ÖH Dalga-31, kulvar fea-cfd, aşama 2/2 bekçileri
"""İki kalemin kilit bekçileri (defter P13B1-03, OH-Z5-19).

Her iddia ters mutasyonla kırmızı kanıtlıdır; kanıt
``docs/scofield/raw/OH/D31/fea-cfd/a2/mutasyon.json``.
"""

import ast
import json
import pathlib
import re
import sys
import warnings

import numpy as np
import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:                                  # pragma: no cover
    sys.path.insert(0, str(KOK))

KANIT = KOK / 'docs/scofield/raw/OH/D31/fea-cfd/a2'


def _sessiz(fn, *a, **k):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **k)


# ===========================================================================
# P13B1-03 — kazanılmamış 1e-12 platform-dışı bandı EMEKLİYE AYRILDI
#
# ÖNCE (once.json / P13B1-03): sevk edilen 5 referansın 5'i darwin/arm64;
# CI ubuntu koştuğu için 5/5 vaka tolerans dalına düşüyordu ve 1e-12 üç
# assert'te GEÇİŞ ÖLÇÜTÜYDÜ. Dosyanın kendi cümlesi bandın ölçülmediğini
# söylüyordu ('ölçüme değil beyana dayanır'). Kapsam dışı hüküm adı
# (not_evaluated) YOKTU, sapmayı rapora yazan kanal YOKTU, bağlayıcı
# belirlenim sözleşmesi bekçi dosyasına BAĞLI DEĞİLDİ (0 test).
#
# Berke karar dosyası §8: seçenek (b), onay sınıfı ANA MODEL KARAR VEREBİLİR.
# ===========================================================================

class TestP13B103BantEmekliye:

    def test_kapsam_KUNYEDEN_okunur_elle_yazilmaz(self):
        """Kapsam tek kaynaktan: referans künyeleri."""
        from tests.cfd import test_euler_bit_ozdesligi as B
        kapsam = B.referans_platform_kapsami()
        assert kapsam, 'kapsam boş — referans envanteri okunamadı'
        # Bugünkü envanter: hepsi TEK platformda (ölçüldü: 5/5 darwin/arm64).
        assert len(kapsam) == 1, kapsam
        # v3.0.0 (15 Eki) — "bu makine kapsamda" eşitliği SÖKÜLDÜ: CI
        # (linux/x86_64) kapsamın DIŞINDADIR ve bu beklenen durumdur; orada
        # vakalar not_evaluated dalına gider (aşağıdaki test). Eşitlik
        # yalnız referans makinede tutuyordu, yani soruyu değil makineyi
        # sınıyordu. Kapsamın künyeden geldiği biçim + teklikle sınanır.
        assert all(re.fullmatch(r'[a-z0-9]+/[A-Za-z0-9_]+', k) for k in kapsam), (
            f'kapsam künyesi platform/mimari biçiminde değil: {kapsam}')
        # Kapsam KOD İÇİNDE literal olarak yazılmamalı (kayarsa kendiliğinden
        # kaysın); 'darwin/arm64' dizesi kaynakta geçmemeli.
        kaynak = (KOK / 'tests/cfd/test_euler_bit_ozdesligi.py').read_text(
            encoding='utf-8')
        govde = '\n'.join(
            l for l in kaynak.splitlines() if not l.strip().startswith('#'))
        assert "'darwin/arm64'" not in govde, 'kapsam elle yazılmış'

    def test_kapsam_disi_hukum_NOT_EVALUATED_assert_ETMEZ(self):
        """Kazanılmamış bant artık hüküm vermiyor; sapma rapora yazılıyor."""
        from tests.cfd import test_euler_bit_ozdesligi as B
        U, meta = B.referans_yukle('izantropik_60x12')
        yabanci = B._kunye_platformlu(meta, yerli=False)
        B.PLATFORM_SAPMA_RAPORU['olcumler'].pop('d31a2', None)

        # 1e-6'lık DAVRANIŞ oynaması: eski kod burada AssertionError atardı.
        bozuk = U.copy()
        bozuk[..., 0] *= 1.0 + 1e-6
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            B._alan_karsilastir(U, bozuk, yabanci, 'd31a2')   # RAISE ETMEMELİ

        kayit = B.PLATFORM_SAPMA_RAPORU['olcumler']['d31a2']
        assert kayit['hukum'] == 'not_evaluated', kayit
        assert kayit['max_bagil_fark'] == pytest.approx(1e-6, rel=1e-3)
        assert kayit['rapor_bandi'] == 1e-12
        assert kayit['rapor_bandi_icinde'] is False
        B.PLATFORM_SAPMA_RAPORU['olcumler'].pop('d31a2', None)

    def test_skaler_ayagi_da_kapsam_disinda_hukum_VERMEZ(self):
        """Skaler ayak da uydurma banda dayanmıyor (ölçülür, yazılır)."""
        from tests.cfd import test_euler_bit_ozdesligi as B
        _U, meta = B.referans_yukle('izantropik_60x12')
        yabanci = B._kunye_platformlu(meta, yerli=False)
        ref = meta['kosum']
        sahte = {
            'iterations': ref['iterations'] + 7,        # yakınsama yolu kaydı
            'converged': ref['converged'],
            'convergence_status': ref.get('convergence_status'),
            'mass_flow_in_kg_s': ref['mass_flow_in_kg_s'] * (1.0 + 1e-5),
            'mass_flow_out_kg_s': ref['mass_flow_out_kg_s'],
            'residual_history': [ref['residual_last']],
        }
        B.PLATFORM_SAPMA_RAPORU['olcumler'].pop('d31a2/skaler', None)
        B._skaler_karsilastir(yabanci, sahte, 'd31a2')        # RAISE ETMEMELİ
        kayit = B.PLATFORM_SAPMA_RAPORU['olcumler']['d31a2/skaler']
        assert kayit['hukum'] == 'not_evaluated'
        assert kayit['iterations_kosum'] == ref['iterations'] + 7
        assert kayit['max_bagil_fark'] == pytest.approx(1e-5, rel=1e-3)
        B.PLATFORM_SAPMA_RAPORU['olcumler'].pop('d31a2/skaler', None)

    def test_kapsam_ICINDE_bit_sarti_DURUYOR(self):
        """Emeklilik kapsam içini GEVŞETMEDİ: 1 ULP hâlâ kırmızı."""
        from tests.cfd import test_euler_bit_ozdesligi as B
        U, meta = B.referans_yukle('izantropik_60x12')
        yerli = B._kunye_platformlu(meta, yerli=True)
        bozuk = U.copy()
        bozuk[0, 0, 0] = np.nextafter(bozuk[0, 0, 0], np.inf)
        with pytest.raises(AssertionError, match='BİT düzeyinde değişti'):
            B._alan_karsilastir(U, bozuk, yerli, 'd31a2-yerli')

    # ÇEVRİLDİ — ÖH D32 / fix-35b (OH-D26-14 üçüncü ayağı). Düğüm adı
    # ``fikstürüne`` -> ``fiksturune``: Türkçe ``ü`` EKRANDA ayırt edilir
    # (homoglif değildir) ama ``pytest dosya::ad`` elle yazıldığında
    # "no tests ran" üretir. İDDİA DEĞİŞMEDİ, gövdeye dokunulmadı;
    # değişen yalnız tanımlayıcının yazımıdır. Türkçe docstring AYNEN
    # kalır — bekçi yalnız düğüm ADINI kapsar.
    def test_BAGLAYICI_sozlesme_belirlenim_fiksturune_bagli(self):
        """Kapsam dışı yol fail-closed — DAVRANIŞLA ölçülür.

        Yapısal ölçüm ('gövdede assert var mı') YETMEZ: ``if False:
        assert ...`` onu geçer (bu bekçinin ilk hâli tam oradan sızdı,
        ters mutasyon 2 yeşil kaldı). Kapının kendisi sentetik hükümle
        çağrılır.
        """
        from tests.cfd import test_euler_bit_ozdesligi as B

        # (a) Fikstür kaçılamaz: oturum kapsamlı + autouse, aracı çağırır.
        kaynak = (KOK / 'tests/cfd/test_euler_bit_ozdesligi.py').read_text(
            encoding='utf-8')
        agac = ast.parse(kaynak)
        fn = next((d for d in ast.walk(agac)
                   if isinstance(d, ast.FunctionDef)
                   and d.name == 'belirlenim_sozlesmesi'), None)
        assert fn is not None, 'belirlenim_sozlesmesi fikstürü YOK'
        sus = ast.dump(ast.Module(body=fn.decorator_list, type_ignores=[]))
        assert "'session'" in sus and 'autouse' in sus, sus[:300]
        assert 'cfd_ci_bit_ozdeslik' in ast.dump(fn), 'araç çağrılmıyor'
        assert 'belirlenim_hukmunu_dogrula' in ast.dump(fn), (
            'fikstür hükmü kapıya sormuyor')

        # (b) Kapı GERÇEKTEN hüküm veriyor: ayrışma → AssertionError.
        ayristi = {'vakalar': {'izantropik_60x12': {
            'hukum': 'AYRISTI', 'bit_ayni': False,
            'max_mutlak_fark': 3.1e-17}}}
        with pytest.raises(AssertionError, match='KURULAMADI'):
            B.belirlenim_hukmunu_dogrula(ayristi, 'linux/x86_64', {'darwin'})

        # (c) Ölçüm hiç koşmadıysa da fail-closed ('ölçemedim' yeşil değil).
        with pytest.raises(AssertionError, match='HİÇ VAKA'):
            B.belirlenim_hukmunu_dogrula({'vakalar': {}}, 'linux/x86_64',
                                         {'darwin'})

        # (d) Bit-aynı hüküm geçer (kapı her şeyi reddetmiyor).
        B.belirlenim_hukmunu_dogrula(
            {'vakalar': {'izantropik_60x12': {'bit_ayni': True}}},
            'linux/x86_64', {'darwin'})

    def test_belirlenim_sozlesmesi_BU_platformda_GERCEKTEN_kuruluyor(self):
        """Sözleşme yalnız bağlanmadı, ÖLÇÜLDÜ: iki ayrı süreç, bit-aynı.

        Ucuz vaka (izantropik 60×12, ölçülen ~5 s/süreç). Kapsam içinde
        bağlayıcı olan saklı referanstır; bu bekçi kapsam DIŞI yolun
        dayandığı önermenin bu makinede de doğru olduğunu ölçer.
        """
        from tools import cfd_ci_bit_ozdeslik as belirlenim
        hukum = belirlenim.kos(['izantropik_60x12'])
        v = hukum['vakalar']['izantropik_60x12']
        assert v['hukum'] == 'BIT-AYNI', v
        assert v['bit_ayni'] is True and v['max_mutlak_fark'] == 0.0, v

    def test_CI_adimi_hala_bagli_ve_fail_closed(self):
        """Bağlayıcı sözleşme CI'dan sessizce düşerse kırmızı."""
        yml = (KOK / '.github/workflows/tests.yml').read_text(encoding='utf-8')
        assert 'tools/cfd_ci_bit_ozdeslik.py' in yml
        arac = (KOK / 'tools/cfd_ci_bit_ozdeslik.py').read_text(
            encoding='utf-8')
        # Ayrışma → çıkış kodu 1 (fail-closed).
        assert 'return 1' in arac and 'OLCULEMEDI' in arac


# ===========================================================================
# OH-Z5-19 — öz-tutarlılık kapısının KAPSAMI kalıcı ve adlı beyan
#
# ÖNCE (once.json / OH-Z5-19, bugünkü ağaçta yeniden üretildi):
#   izantropik  60×12 :        1,00×  (operatör canlı, kusur yok)
#   şoklu       60×12 :       44,29×  → kapı genişlerse converged True→False
#   şoklu      120×24 :      398,71×  → aynı
#   izantropik 120×24 : 2,9030e+07×   → aynı
# Kapsam sabiti YOKTU, kapsam yayımlanmıyordu, kapsam dışı hükmü adlandıran
# alan YOKTU ve 'selfconsistency_gate' None dönüşü "kapı yok" ile "kapı
# kapsamıyor"u karıştırıyordu.
#
# ENGEL (D31'de kalem 'kismen'): kapsamı açık yola genişletmek 3/4
# referansta converged bayrağını devirir; §11.3 referanslarının
# yenilenmesi P10B4-14 (Berke) ile KİLİTLİ idi.
#
# ENGEL D32'DE KALKTI: Berke 15 Eyl 2026 §3 seçenek (A) — üç durumlu
# yakınsama sözleşmesi. Kapı GENİŞLETİLMEDİ (kök onarım 2.7'de), ama
# kapsam dışında verilen hüküm artık GERİ ÇEKİLİYOR (converged=None,
# convergence_status='not_evaluated') ve dört künye P10B4-14 deseniyle
# yenilendi (diziler bit-aynı). Aşağıdaki kapsam beyanı bekçileri aynen
# duruyor; hüküm ayağı OH-D31-15 yönüyle güncellendi.
# ===========================================================================

@pytest.fixture(scope='module')
def sok_60x12_kosumu():
    from tests.cfd.conftest import euler_referans_coz
    return _sessiz(euler_referans_coz, 'sok_60x12')


@pytest.fixture(scope='module')
def izantropik_120x24_kosumu():
    from tests.cfd.conftest import euler_referans_coz
    return _sessiz(euler_referans_coz, 'izantropik_120x24')


class TestOHZ519KapsamBeyani:

    def test_kapsam_TEK_KAYNAK_sabiti_ve_YAYIMLANIYOR(self, sok_60x12_kosumu):
        from hrma.cfd.steady import SELFCONSISTENCY_GATE_SCOPE
        _g, s = sok_60x12_kosumu
        ss = s['slope_state']
        assert ss['selfconsistency_gate_scope'] == SELFCONSISTENCY_GATE_SCOPE
        # Sabit, kapının GERÇEK koşulunu anlatmalı (ikisi ayrışamaz).
        assert 'line_implicit_j' in SELFCONSISTENCY_GATE_SCOPE
        assert 'second_order' in SELFCONSISTENCY_GATE_SCOPE
        metin = (KOK / 'hrma/cfd/steady.py').read_text(encoding='utf-8')
        blok = metin.split('selfconsistency_gate_active = bool(', 1)[1]
        blok = blok.split(')', 1)[0]
        for parca in SELFCONSISTENCY_GATE_SCOPE.split('+'):
            assert parca in blok, (
                f'kapsam sabiti ({SELFCONSISTENCY_GATE_SCOPE}) kapının '
                f'gerçek koşulundan ({blok.strip()}) ayrışmış')

    def test_None_BELIRSIZLIGI_kalkti(self, sok_60x12_kosumu):
        """'kapı yok' ile 'kapı KAPSAMIYOR' artık ayrı okunur."""
        _g, s = sok_60x12_kosumu
        ss = s['slope_state']
        assert ss['selfconsistency_gate'] is None      # açık yol (eski alan)
        assert ss['in_gate_scope'] is False            # AMA sebebi ADIYLA
        assert isinstance(ss['selfconsistency_gate_scope'], str)

    def test_sok_60x12_artik_CANLI_operatorle_yakinsiyor(self, sok_60x12_kosumu):
        """ÖH D37 A3a cfd-kok-a (OH-DK-12/13; Berke Sunum 3a onayı 24 Eyl):
        şoklu akışta plato-dondurması kapandı → bu vaka artık canlı
        operatörle yakınsar; hüküm kazanılmıştır (şema = yayım 2,0e-6)."""
        _g, s = sok_60x12_kosumu
        assert s['converged'] is True
        assert s['convergence_status'] == 'converged'
        assert s['scheme_residual_exceeds_tol'] is False

    def test_ACIK_yolda_hukum_KAPSAM_DISI_adiyla_ve_SAYIYLA(
            self, izantropik_120x24_kosumu):
        """Kusur giderilmedi ama gizlenmiyor: bayrak + ölçülen oran.

        ÖH D37 A3a cfd-kok-a: vaka sok_60x12'den izantropik_120x24'e taşındı
        (sok_60x12 artık canlı operatörle yakınsıyor); kapsam dışı dondurma
        yolunda biten referans bu."""
        from tests.cfd.conftest import EULER_REFERANS_VAKALARI
        _g, s = izantropik_120x24_kosumu
        ss = s['slope_state']
        tol = float(EULER_REFERANS_VAKALARI['izantropik_120x24']['cozucu']['tol_res'])
        yayim = float(np.asarray(s['residual_history'])[-1])
        sema = float(s['scheme_residual_norm'])

        # --- ÇEVRİLDİ (ÖH D32 / OH-D31-15) ---------------------------
        # D31'de bu mandal bilerek "bayrak DÖNMEMELİ" diyordu: engel,
        # §11.3 referanslarının P10B4-14 (Berke) kilidiydi. D32'de o ŞART
        # YERİNE GELDİ — Berke 15 Eyl 2026 §3'te seçenek (A)'yı onayladı,
        # dört künye P10B4-14 deseniyle yenilendi (diziler BİT-AYNI,
        # sha256 doğrulandı: docs/scofield/raw/OH/D32/fea-cfd/a2/
        # kunye_yenileme.json) ve çözücü artık kapsam dışında HÜKÜM
        # VERMİYOR. Mandal bu yüzden kusuru koruyan bekçi konumuna
        # düştü; yönü çevrildi. Kapsam beyanının KENDİSİ (aşağıdaki
        # alanlar + ölçülen oran) aynen kilitli kalıyor — beyan
        # kaldırılmadı, üstüne hüküm geri çekilmesi EKLENDİ.
        assert s['converged'] is None, (
            'kapsam DIŞINDA yine hüküm yayımlanıyor — OH-D31-15 onarımı '
            'geri alınmış olabilir')
        assert s['convergence_status'] == 'not_evaluated', (
            f"hüküm cinsi {s['convergence_status']!r}; kapsam dışı koşu "
            f"'not_evaluated' demek zorunda")
        assert s['scheme_residual_exceeds_tol'] is True
        assert yayim < tol
        # Hüküm kapının DIŞINDA verildi ve bu ADIYLA yayımlanıyor.
        assert ss['verdict_outside_gate_scope'] is True, (
            'kapsam dışı hüküm bayrağı düşmüş — kusur yine sessiz')
        assert ss['blocks_verdict'] is False
        # Ölçülen oran yayımlanıyor ve D30/D31 ölçümüyle uyuşuyor.
        oran = ss['scheme_over_published_ratio']
        assert oran == pytest.approx(sema / yayim, rel=1e-9)
        # ÖLÇÜLDÜ (ARA KAYIT 7 dondurma koşusu, izantropik_120x24: şema
        # 2,118e-4 / yayım 7,221e-12): ~2,93e7×. (D31 a2 sok_60x12: 44,288×.)
        assert oran == pytest.approx(2.933e7, rel=0.05), (
            f'yayım ⟷ şema farkı {oran:.4g}× — ölçüm ≈2,93e7× idi')

    def test_KAPSAM_ICINDE_bayrak_DUSMELI(self):
        """Bayrak 'her koşumda True' değil: kapsam içinde False.

        Ucuz örtük koşum (20×6, 40 iterasyon): yakınsamaz, ama kapsam
        İÇİNDEDİR — kapsam dışı bayrağı bu yüzden False olmalıdır.
        """
        from hrma.cfd.steady import solve_steady_axisym
        from tests.cfd.conftest import lule_gridi, IZANTROPIK_COZUCU
        grid = lule_gridi(20, 6)
        ayar = dict(IZANTROPIK_COZUCU, max_iters=40)
        s = _sessiz(solve_steady_axisym, grid, time_integrator='line_implicit_j',
                    second_order=True, **ayar)
        ss = s['slope_state']
        assert ss['in_gate_scope'] is True
        assert ss['selfconsistency_gate'] == 'line_implicit_j'
        assert ss['verdict_outside_gate_scope'] is False, (
            'kapsam içindeyken kapsam-dışı bayrağı True — bayrak sabit '
            'True yazılmış olabilir')

    def test_ENGEL_kaydi_ve_olcum_dosyasi_duruyor(self):
        """Kalem 'kismen': engel ADIYLA kayıtlı, sayılar dosyada."""
        metin = (KOK / 'hrma/cfd/steady.py').read_text(encoding='utf-8')
        assert 'OH-Z5-19' in metin and 'P10B4-14' in metin
        d = json.loads((kanit_gerekli(KANIT / 'once.json')).read_text(encoding='utf-8'))
        z = d['OH-Z5-19']
        assert z['K8_dusen_sayi'] == 3 and z['K8_toplam'] == 4
        assert sorted(z['K8_kapi_genisletilirse_hukmu_dusen']) == [
            'izantropik_120x24', 'sok_120x24', 'sok_60x12']
        for k, v in z['K8_vakalar'].items():
            assert v['yayimlanan_converged'] is True, k


def test_dokunulan_dosyalar_AST_gecerli():
    """Kesinti denetimi (CLAUDE.md §27.1): yarım Edit bırakılmamış."""
    for yol in ('hrma/cfd/steady.py', 'tests/cfd/test_euler_bit_ozdesligi.py'):
        agac = ast.parse((KOK / yol).read_text(encoding='utf-8'))
        assert [d for d in ast.walk(agac)
                if isinstance(d, (ast.FunctionDef, ast.ClassDef))], yol
