# -*- coding: utf-8 -*-
"""D15 / cfd-picard aşama 2 — ÜRÜN TESTLERİNİN HÜKÜM SÖZLEŞMESİ.

NE KAPANDI (ÖH defter OH-Z5-14'ün kalan yarısı, D15-CFD-02)
------------------------------------------------------------
Aşama 1 plato MAKİNESİNİ kurdu (``convergence_status`` +
``convergence_plateau``) ama ``elif scheme_plateau['detected']`` dalını
GERÇEK bir vakada gören bekçi yoktu; a1 raporu bunu beyanla açık
bıraktı. O dalın asıl bekçisi ``tests/cfd``deki BEŞ kırmızı testin
hüküm sözleşmesine ÇEVRİLMESİDİR ve bu aşamada yapıldı:

  test_ayrilma.py::test_BASAMAK13_ayrilmali_vakada_dort_uye_AYNI_ciktida
      → converged=False + status='plateau' + plato bloğu (ÖLÇÜLDÜ)
  test_korunum.py::test_viskoz_butce_KAPANISI
      → premis fail-closed + TAVAN durumu kapanış çıpası
  test_viskoz_entegrasyon.py::test_KAPI_limit_dongusu_EGIM_DONDURMASIYLA_kirilir
      → dondurma ateşliyor ama hüküm KAZANDIRMIYOR (ölçüldü)
  test_wall_output.py::test_kunye_kosumu_ADIYLA_tasir
      → künye ÇÖZÜCÜYÜ TEKRARLAR (kimlik sınavı), hüküm üretmez
  test_wall_output.py::test_kok_regresyon_cipasi
      → çıpa hükümden hükümsüzlüğün CİNSİNE + ölçülen köke taşındı

BU DOSYA NEYİ TUTAR (hepsi UCUZ — çözücü koşmaz)
-------------------------------------------------
  1. ÇEVİRİ GERİ ALINAMAZ: beş testin gövdesi AST'den okunur ve hüküm
     sözleşmesinin şartlarını GERÇEKTEN taşıdığı doğrulanır. Kırmızıyı
     "assert'i silerek" ya da ``converged is True``a geri döndürerek
     kapatan bir düzenleme burada yakalanır.
  2. ÇIPA ↔ ÖLÇÜM BAĞI (TEK KAYNAK): tests/cfd'ye yazılan sayılar bu
     kulvarın kanıt dosyalarındaki ÖLÇÜMLERLE karşılaştırılır; bekçi
     ile kanıt sessizce ayrışamaz.
  3. TOLERANS ≥ FAZ DUYARLILIĞI: her çıpanın toleransı, koşunun bir
     iterasyon erken/geç bitmesinin ÖLÇÜLEN etkisinden büyük olmalıdır
     (yoksa bekçi kırılgandır, kusur bulmaz gürültü bulur).
  4. OH-Z5-19 ÖLÇÜM KAYDI: açık yol kapı kapsamına alınsaydı hangi
     bit-özdeşlik referanslarının hükmü geri çekilirdi — sayı dondurulur
     (karar Berke'de; bu dosya KARAR VERMEZ, ölçümü kaybolmaktan korur).
"""
import ast
import json
import os

import pytest
from tests.support.kanit import kanit_gerekli

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANIT = os.path.join(REPO, 'docs', 'scofield', 'raw', 'OH', 'D15',
                     'cfd-picard', 'a2')
ONCE = os.path.join(KANIT, 'once.json')
FAZ = os.path.join(KANIT, 'faz_duyarliligi.json')
Z519 = os.path.join(KANIT, 'oh_z5_19_olcum.json')
Z519E = os.path.join(KANIT, 'oh_z5_19_etki.json')


def _oku(yol):
    with open(yol, encoding='utf-8') as f:
        return json.load(f)


def _govde(dosya, ad):
    """``dosya`` içindeki ``ad`` fonksiyonunun assert satırları (metin)."""
    yol = os.path.join(REPO, dosya)
    with open(yol, encoding='utf-8') as f:
        agac = ast.parse(f.read(), filename=yol)
    for d in ast.walk(agac):
        if isinstance(d, ast.FunctionDef) and d.name == ad:
            return [ast.unparse(n) for n in ast.walk(d)
                    if isinstance(n, ast.Assert)]
    raise AssertionError(f'{dosya} içinde {ad} yok — test yeniden '
                         f'adlandırılmış ya da silinmiş olabilir')


#: Çevrilen beş test ve gövdelerinin TAŞIMAK ZORUNDA olduğu şartlar.
#: Şartlar ``ast.unparse`` biçimindedir (tek tırnak, normalize boşluk).
CEVIRI_SARTLARI = {
    ('tests/cfd/test_ayrilma.py',
     'test_BASAMAK13_ayrilmali_vakada_dort_uye_AYNI_ciktida'): (
        "res['converged'] is False",
        "res['convergence_status'] == 'plateau'",
        "res['scheme_residual_blocks_verdict'] is True",
        "pl['detected'] is True",
        "pl['relative_spread'] < pl['rel_tol']",
        "pl['window_iterations'] >= pl['probe_every']",
        'AYR_PLATO_KALINTI',
        "' PLATO:' in res['convergence_basis']",
        "'HÜKÜM VERİLMEDİ' in res['convergence_basis']",
    ),
    ('tests/cfd/test_korunum.py', 'test_viskoz_butce_KAPANISI'): (
        "res['converged'] is False",
        "res['convergence_status'] == 'not_converged'",
        "res['scheme_residual_blocks_verdict'] is True",
        'VISKOZ_TAVAN_ENERJI_KAPANIS',
        'VISKOZ_TAVAN_KUTLE_KAPANIS',
        'VISKOZ_SIZINTI_IMZASI',
    ),
    ('tests/cfd/test_viskoz_entegrasyon.py',
     'test_KAPI_limit_dongusu_EGIM_DONDURMASIYLA_kirilir'): (
        "sonuc['converged'] is False",
        "sonuc['convergence_status'] == 'not_converged'",
        "sonuc['scheme_residual_blocks_verdict'] is True",
        "sonuc['convergence_plateau']['detected'] is False",
        'KAPI_DONDURMA_ITER',
        'KAPI_GEVSEK_SEMA_KALINTI',
        "siki['converged'] is False",
        'KAPI_SIKI_SEMA_KALINTI',
        'KAPI_HUKUM_NOTRLUK_MAKS',
    ),
    ('tests/cfd/test_wall_output.py', 'test_kunye_kosumu_ADIYLA_tasir'): (
        "k['converged'] is izo['converged']",
        "k['converged'] is False",
        "k['convergence_basis'] == izo['convergence_basis']",
        "'HÜKÜM VERİLMEDİ' in k['convergence_basis']",
        "'scheme_residual_norm' in k['convergence_basis']",
    ),
    ('tests/cfd/test_wall_output.py', 'test_kok_regresyon_cipasi'): (
        "izo['converged'] is False",
        "izo['convergence_status'] == 'not_converged'",
        "izo['scheme_residual_blocks_verdict'] is True",
        "izo['convergence_plateau']['detected'] is False",
        'VLULE_TAVAN_SEMA_KALINTI',
        'VLULE_MDOT',
    ),
}


@pytest.mark.parametrize('anahtar', sorted(CEVIRI_SARTLARI),
                         ids=lambda a: f'{os.path.basename(a[0])}::{a[1]}')
class TestCeviriGeriAlinamaz:
    """Hüküm sözleşmesi testin GÖVDESİNDE duruyor mu? (AST, çözücüsüz)"""

    def test_sartlarin_HEPSI_govdede(self, anahtar):
        dosya, ad = anahtar
        govde = '\n'.join(_govde(dosya, ad))
        eksik = [s for s in CEVIRI_SARTLARI[anahtar] if s not in govde]
        assert not eksik, (
            f'{dosya}::{ad} hüküm sözleşmesinin şartlarını kaybetti: '
            f'{eksik} — kırmızı, assert silinerek ya da eski iddiaya '
            f'dönülerek kapatılmış olabilir')

    def test_ESKI_iddia_geri_gelmemis(self, anahtar):
        """``converged is True`` ürünün ARTIK VERMEDİĞİ hükümdür."""
        dosya, ad = anahtar
        for satir in _govde(dosya, ad):
            assert "['converged'] is True" not in satir, (
                f'{dosya}::{ad} yeniden "converged is True" diyor: '
                f'{satir}')


class TestCipaOlcumeBagli:
    """tests/cfd'ye yazılan sayı, kanıt dosyasındaki ÖLÇÜMÜN kendisi mi?"""

    def test_izo_cipalari(self):
        from tests.cfd.test_wall_output import (VLULE_MDOT,
                                                VLULE_TAVAN_ITER,
                                                VLULE_TAVAN_SEMA_KALINTI)
        o = _oku(kanit_gerekli(ONCE))['izo']
        assert o['iterations'] == VLULE_TAVAN_ITER
        assert o['cipa']['mass_flow_in_kg_s'] == pytest.approx(
            VLULE_MDOT, rel=1e-6)
        assert o['sema_kalinti'] == pytest.approx(
            VLULE_TAVAN_SEMA_KALINTI, rel=1e-3)
        # Ölçüm, hükümsüzlüğün cinsini de kaydetmiş olmalı.
        assert o['converged'] is False
        assert o['convergence_status'] == 'not_converged'
        assert o['plato_detected'] is False

    def test_butce_cipalari(self):
        from tests.cfd.test_korunum import (VISKOZ_TAVAN_ENERJI_KAPANIS,
                                            VISKOZ_TAVAN_KUTLE_KAPANIS,
                                            VISKOZ_TAVAN_KAPANIS_REL)
        b = _oku(kanit_gerekli(ONCE))['izo']['butce']
        assert b['enerji_kapanis'] == pytest.approx(
            VISKOZ_TAVAN_ENERJI_KAPANIS, rel=VISKOZ_TAVAN_KAPANIS_REL)
        assert b['kutle_kapanis'] == pytest.approx(
            VISKOZ_TAVAN_KUTLE_KAPANIS, rel=VISKOZ_TAVAN_KAPANIS_REL)

    def test_plato_cipasi(self):
        from tests.cfd.test_ayrilma import AYR_PLATO_KALINTI
        a = _oku(kanit_gerekli(ONCE))['ayrilmali']
        assert a['convergence_status'] == 'plateau'
        assert a['plato_detected'] is True
        assert a['plato_kalinti'] == pytest.approx(AYR_PLATO_KALINTI,
                                                   rel=a['plato_rel_tol'])
        # Platonun ÜÇ koşulu ölçümde de sağlanmış olmalı.
        assert a['plato_pencere'] >= a['plato_probe_every']
        assert len(a['plato_ornek']) == a['plato_min_samples']
        assert a['plato_yayilim'] < a['plato_rel_tol']

    def test_kapi_cipalari(self):
        from tests.cfd.test_viskoz_entegrasyon import (
            KAPI_DONDURMA_ITER, KAPI_GEVSEK_SEMA_KALINTI,
            KAPI_HUKUM_NOTRLUK_MAKS, KAPI_SIKI_SEMA_KALINTI)
        d = _oku(kanit_gerekli(ONCE))
        g, s = d['kapi_gevsek'], d['kapi_siki']
        assert g['frozen_at'] == s['frozen_at'] == KAPI_DONDURMA_ITER
        assert g['sema_kalinti'] == pytest.approx(KAPI_GEVSEK_SEMA_KALINTI,
                                                  rel=1e-3)
        assert s['sema_kalinti'] == pytest.approx(KAPI_SIKI_SEMA_KALINTI,
                                                  rel=1e-3)
        notrluk = abs(s['mass_flow_in_kg_s'] / g['mass_flow_in_kg_s'] - 1.0)
        assert notrluk < KAPI_HUKUM_NOTRLUK_MAKS
        # Bant ölçümün en az bir katı payla üstünde olmalı (kırılgan değil).
        assert KAPI_HUKUM_NOTRLUK_MAKS > 2.0 * notrluk


class TestToleransFazDuyarliligiUstunde:
    """Kırılgan çıpa bekçi değildir: bant, ölçülen faz gürültüsünü aşmalı.

    Koşu artık max_iters TAVANINDA bittiğinden alan, minmod limit
    döngüsünün o andaki fazıdır. Bir iterasyon erken/geç bitmenin
    ÖLÇÜLEN etkisi (faz_duyarliligi.json) her çıpanın toleransından
    KÜÇÜK olmalıdır — değilse bekçi kusuru değil gürültüyü ölçer.
    """

    def test_debi_cipasi_gurultunun_ustunde(self):
        y = _oku(kanit_gerekli(FAZ))['ozet']['mass_flow_in_kg_s']['bagil_yayilim']
        assert y < 1e-6, f'debi çıpasının 1e-6 bandı faz gürültüsü {y:.2e}'

    def test_butce_cipasi_gurultunun_ustunde(self):
        from tests.cfd.test_korunum import VISKOZ_TAVAN_KAPANIS_REL
        o = _oku(kanit_gerekli(FAZ))['ozet']
        for ad in ('enerji_kapanis', 'kutle_kapanis'):
            y = o[ad]['bagil_yayilim']
            assert y < VISKOZ_TAVAN_KAPANIS_REL, (
                f'{ad} faz gürültüsü {y:.2e}, bant '
                f'{VISKOZ_TAVAN_KAPANIS_REL:.0e} — çıpa kırılgan')

    def test_sema_kalintisi_cipalanabilir(self):
        y = _oku(kanit_gerekli(FAZ))['ozet']['sema_kalinti']['bagil_yayilim']
        assert y < 1e-3

    def test_YAYIMLANAN_kalinti_cipalanamaz_ADIYLA(self):
        """Neden yayımlanan kalıntıya çıpa KONMADIĞININ ölçümü."""
        o = _oku(kanit_gerekli(FAZ))['ozet']
        assert o['yayimlanan_kalinti']['bagil_yayilim'] > 1e-2, (
            'yayımlanan kalıntının faz gürültüsü küçülmüş — o hâlde ona '
            'da çıpa konabilir ve bu dosyanın gerekçesi güncellenmelidir')
        # Ve şemanınkinden EN AZ altı mertebe gürültülü olmalı: çıpanın
        # neden şemaya konduğunun sayısal gerekçesi.
        assert (o['yayimlanan_kalinti']['bagil_yayilim']
                > 1e6 * o['sema_kalinti']['bagil_yayilim'])


class TestOHZ519OlcumKaydi:
    """AÇIK yol kapı kapsamına alınsaydı hangi referans hükmünü yitirirdi?

    ÖLÇÜM YALNIZCA — referans YENİLENMEZ, kapı DEĞİŞTİRİLMEZ (karar
    Berke'de). Bu bekçi ölçümün kaybolmasını ve sessizce kaymasını
    engeller.
    """

    def test_dort_referansin_UCU_hukmunu_yitirirdi(self):
        d = _oku(kanit_gerekli(Z519))
        assert d['ozet']['toplam_vaka'] == 4
        assert d['ozet']['hukmu_geri_cekilecekler'] == [
            'izantropik_120x24', 'sok_120x24', 'sok_60x12']
        assert d['ozet']['etkilenmeyenler'] == ['izantropik_60x12']

    def test_kapi_bugun_ACIK_YOLU_kapsamiyor(self):
        """Bugünkü ürün: açık yolda kapı hüküm geri çekmiyor (beyanlı)."""
        for kunye, v in _oku(kanit_gerekli(Z519))['B_acik_referans'].items():
            assert v['blocks_verdict'] is False, kunye
            assert v['gate_active'] is None, kunye
            assert v['converged'] is True, kunye

    def test_yitirenlerin_hepsi_DONMUS_operatorden(self):
        """Hükmü yitirecek üçünün ortak imzası ÖLÇÜLDÜ: donmuş eğimler."""
        d = _oku(kanit_gerekli(Z519))
        for kunye in d['ozet']['hukmu_geri_cekilecekler']:
            v = d['B_acik_referans'][kunye]
            assert v['residual_operator'] == 'frozen_slopes', kunye
            assert v['frozen_at'] is not None, kunye
            assert v['sema_tolun_kati'] > 1.0, kunye
        temiz = d['B_acik_referans']['izantropik_60x12']
        assert temiz['residual_operator'] == 'scheme_live_minmod'
        assert temiz['frozen_at'] is None

    def test_ETKI_ALANI_sayiyla_kayitli(self):
        """Kararın MALİYETİ: kaç bekçi, kaç dondurulmuş referans?

        ÖLÇÜLDÜ (olcum_Z519_etki.py, AST taraması): hükmünü yitirecek üç
        referansın oturum fikstürlerini kullanan 26 testten BEŞİ doğrudan
        ``converged is True`` / hüküm kesinliği iddiası taşıyor; dört
        dondurulmuş ``.npz`` referansından ÜÇÜ yeniden üretilmek
        zorunda kalırdı. Bu sayı, "açık yol da kapıya alınsın mı"
        sorusunun fiyatıdır ve kaybolmamalıdır.
        """
        e = _oku(kanit_gerekli(Z519E))
        assert e['yitiren_referanslar'] == _oku(kanit_gerekli(Z519))['ozet'][
            'hukmu_geri_cekilecekler']
        assert e['etkilenen_bekci_sayisi'] == 5
        assert {(b['dosya'], b['test']) for b in e['etkilenen_bekciler']} == {
            ('tests/cfd/test_ayrilma.py', 'test_gercek_cozum_ayrilma_istasyonu'),
            ('tests/cfd/test_ayrilma.py', 'test_gercek_cozum_beyanlari'),
            ('tests/cfd/test_izantropik_lule.py', 'test_yakinsama_beyani'),
            ('tests/cfd/test_korunum.py', 'test_kutle_akisi_dengesi'),
            ('tests/cfd/test_normal_sok.py', 'test_yakinsama_ve_rejim'),
        }
        npz = [d for d in e['dondurulmus_referans_dosyalari']
               if d['dosya'].endswith('.npz')]
        assert len(npz) == 4
        assert sum(1 for d in npz if d['kunye_yitirir']) == 3
