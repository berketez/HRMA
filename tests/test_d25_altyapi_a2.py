# -*- coding: utf-8 -*-
"""ÖH Dalga-25 · kulvar ALTYAPI · aşama a2 — bekçiler.

Kapsanan defter kalemleri
-------------------------
P17B1-17   ``sayfalar.py`` sıvı yapısal panelinin "köşe tekilliği
           yakınsamıyor" borcunu KAPANDI ilan ediyor; canlı ölçüm açık diyor
P10B3-23   Fable-D19 ŞARTI: kurucu dizin doğrulamasının DALLANMA YÖNÜ
OH-D24-06  PK6 üç-motor çapa şablonu ``/api/fea/structural`` köprü ucunu
           çağırmıyor — köprü hükmü çapada görünmüyor

Her bekçi ters-mutasyonla kanıtlandı:
``docs/scofield/raw/OH/D25/altyapi/a2/mutasyon.json``.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from tests.support.kanit import kanit_gerekli

DEPO = pathlib.Path(__file__).resolve().parents[1]
SAYFALAR = DEPO / 'tools' / 'browser_harness' / 'sayfalar.py'
DENETIMLER = DEPO / 'tools' / 'browser_harness' / 'denetimler.py'
NSI = DEPO / 'packaging' / 'hrma.nsi'
D17_BEKCI = DEPO / 'tests' / 'test_d17_altyapi_a1.py'
CAPA_SABLONU = DEPO / 'docs/scofield/raw/OH/Z5S/pk6/capa_kosumu.py'
KANIT = DEPO / 'docs/scofield/raw/OH/D25/altyapi/a2'
ONCE = KANIT / 'once_p17b117.json'


def _katla(m: str) -> str:
    """Türkçe-güvenli harf katlaması (ölçüm betiğinin aynısı).

    ``str.lower()`` 'İ'yi birleşen noktalı 'i̇'ye çevirir; künye BÜYÜK
    HARFLE yazıldığında blok sayımı sessizce sıfırlanırdı.
    """
    return m.replace('İ', 'i').replace('I', 'ı').lower()


def _yorum_bloklari(metin: str):
    """Ardışık yorum satırlarını TEK bloğa toplar.

    İddia iki satıra bölünmüştü ("…borcu\\n#: kapandı"); satır satır arama
    onu kaçırıyordu. Blok birleştirmesi ölçümün (olcum_p17b117.py) aynısıdır.
    """
    bloklar, kova = [], []
    for satir in metin.split('\n'):
        s = satir.strip()
        if s.startswith('#'):
            kova.append(s.lstrip('#: ').rstrip())
        else:
            if kova:
                bloklar.append(' '.join(kova))
                kova = []
    if kova:
        bloklar.append(' '.join(kova))
    return bloklar


# ---------------------------------------------------------------------------
# P17B1-17 — turun tarif dosyası borcu KAPANDI diye yazamaz
# ---------------------------------------------------------------------------

class TestP17B117KoseTekilligiBorcu:

    @staticmethod
    def _tekillik_bloklari():
        return [b for b in _yorum_bloklari(SAYFALAR.read_text(encoding='utf-8'))
                if 'köşe tekilliği' in _katla(b)]

    def test_bloklar_duruyor(self):
        """Adres göçtüyse aşağıdaki iddialar sessizce boşa düşmesin."""
        assert self._tekillik_bloklari(), (
            'sayfalar.py`de "köşe tekilliği" geçen yorum bloğu KALMADI — '
            'bekçi hiçbir şeyi ölçmüyor demektir (adres göçtü)')

    def test_borc_KAPANDI_denmiyor(self):
        kapandi = re.compile(r'kapan(dı|mış|mıştır)')
        suclular = [b for b in self._tekillik_bloklari() if kapandi.search(b)]
        assert not suclular, (
            'sıvı yapısal panelinin köşe tekilliği borcu KAPANDI ilan '
            'ediliyor; ölçüm (once_p17b117.json) borcun AÇIK olduğunu '
            'söylüyor: canlı turda tepe von Mises 1763,7 MPa (borç açıldığı '
            'gün 1742 MPa) ve MIN SF 0,07; köprü taramasında 3 tasarım '
            f'noktasının 2`si yayımlanan kipte yakınsamıyor.\n{suclular}')

    def test_borc_ACIK_diye_beyan_ediliyor(self):
        bloklar = self._tekillik_bloklari()
        assert any(re.search(r'\bAÇIK\b', b) for b in bloklar), (
            'borcun AÇIK olduğu hiçbir blokta yazmıyor — "kapandı"yı silmek '
            'yetmez, tarif dosyası gerçeği SÖYLEMELİ')

    def test_olculen_sayilar_yaziyor(self):
        """Beyan gerekçesiz olamaz: tepe gerilme ve emniyet katsayısı."""
        hepsi = ' '.join(self._tekillik_bloklari())
        for sayi in ('1763,7', '1742', '0,07'):
            assert sayi in hepsi, (
                f'ölçülen {sayi} sayısı künyede yok — sayısız beyan, '
                'kanıtsız iddianın öbür yüzüdür')

    def test_kanit_yolu_yaziyor(self):
        hepsi = ' '.join(self._tekillik_bloklari())
        assert 'docs/scofield/raw/OH/D25/altyapi/a2/once_p17b117.json' in hepsi, (
            'künye ölçüm dosyasını göstermiyor — okuyucu sayıyı '
            'doğrulayamaz')
        assert 'tour_report.json' in hepsi, (
            'canlı tur kaydı (D24 altyapı a2) künyede gösterilmiyor')

    def test_olcum_dosyasi_borcu_ACIK_olculuyor(self):
        """Künyedeki sayı ölçümün KENDİSİYLE çaprazlanır."""
        assert kanit_gerekli(ONCE).exists(), f'{ONCE} yok — künye kanıtsız kalır'
        d = json.loads(kanit_gerekli(ONCE).read_text(encoding='utf-8'))
        kopru = d['kopru']
        assert kopru['borc_kapandi_iddiasi_tutuyor_mu'] is False, (
            'ölçüm "borç kapandı" diyor ama künye AÇIK diyor — ikisinden '
            'biri bayat')
        assert kopru['yakinsamayan'] >= 1 and kopru['toplam_olculen'] >= 3
        sivi = d['canli_tur']['sayfalar']['liquid']
        assert abs(sivi['tepe_von_mises_MPa'] - 1763.7) < 0.05
        assert abs(sivi['min_sf'] - 0.07) < 0.005
        iddia = d['iddia']['tools/browser_harness/sayfalar.py']
        assert iddia['borc_kapandi_iddiasi'] == 2, (
            'ölçüm ONARIM ÖNCESİ hâli göstermeli (2 iddia); dosya yeniden '
            'koşulup üzerine yazılmış olabilir')

    def test_turun_yakinsama_caprazi_YERINDE(self):
        """Künye "kapı zaten var" diyor — o kapının varlığı sınanır.

        Onarım künyeyi düzeltmekle yetiniyor; gerekçesi, yakınsama
        beyanının turda ZATEN çaprazlandığıdır (renk + tur + yüzde). O
        çapraz sökülürse künyedeki gerekçe yalan olur.
        """
        kod = DENETIMLER.read_text(encoding='utf-8')
        i = kod.find("if panel_adi == 'yapisal'")
        if i < 0:
            i = kod.find("_capraz_beklentileri")
        assert i >= 0, 'çapraz türetimi bulunamadı (adres göçtü)'
        dilim = kod[i:kod.find("elif panel_adi == 'termal'", i)]
        assert 'yakınsama hükmü (yakınsadı)' in dilim, (
            'yapısal panelin YAKINSADI beklentisi çaprazdan düşmüş')
        assert 'yakınsama hükmü (yakınsamadı)' in dilim, (
            'yapısal panelin YAKINSAMADI beklentisi çaprazdan düşmüş')
        assert "haric=('NOT CONVERGED', 'YAKINSAMADI')" in dilim, (
            '"CONVERGED" imzası "NOT CONVERGED"i de yakalar; negatif bağlam '
            'olmadan yakınsamayan koşum yakınsamış sayılır')


# ---------------------------------------------------------------------------
# P10B3-23 — Fable-D19 ŞARTI: dallanma YÖNÜ
# ---------------------------------------------------------------------------

class TestP10B323DallanmaYonu:

    @staticmethod
    def _secmain():
        kod = '\n'.join(s for s in NSI.read_text(encoding='utf-8').split('\n')
                        if not s.lstrip().startswith(';'))
        i = kod.find('Section "HRMA" SecMain')
        assert i >= 0, 'SecMain bölümü yok'
        return kod[i:kod.find('SectionEnd', i)]

    def test_kullanilabilir_dali_Abortu_ATLIYOR(self):
        """ÜRÜN iddiası: `StrCmp $R0 "1" <etiket>` + etiket Abort`tan SONRA.

        ŞART metni bunu D17 bekçisine yazdırıyor; burada AYNI değişmez
        ürün tarafında bağımsız sınanır (D17 bekçisi silinse bile kusur
        yakalanır).
        """
        kurulum = self._secmain()
        i_cagri = kurulum.find('Call HrmaDizinKullanilabilirMi')
        assert i_cagri >= 0, 'SecMain doğrulamayı çağırmıyor'
        izleyen = kurulum[i_cagri:].split('\n')[1]
        m = re.match(r'\s*StrCmp\s+\$R0\s+"1"\s+(\w+)\s*$', izleyen)
        assert m, (
            'çağrıyı izleyen satır `StrCmp $R0 "1" <etiket>` değil — '
            f'dallanmanın yönü doğrulanamıyor:\n{izleyen!r}')
        etiket = m.group(1)
        i_strcmp = i_cagri + kurulum[i_cagri:].find('StrCmp')
        i_abort = kurulum.find('Abort', i_strcmp)
        m_et = re.search(r'^\s*%s:' % re.escape(etiket), kurulum[i_strcmp:], re.M)
        assert i_abort > i_strcmp and m_et, 'Abort ya da etiket tanımı yok'
        assert i_abort < i_strcmp + m_et.start(), (
            f'`{etiket}:` tanımı Abort`tan ÖNCE — "kullanılabilir" dalı '
            'Abort`u atlamıyor, doğrulama hiçbir şeyi engellemiyor')

    def test_SART_iddiasi_D17_bekcisinde_DURUYOR(self):
        """Fable-D19 ŞARTI metnen yerine getirildi mi (silinemez olsun)."""
        kod = D17_BEKCI.read_text(encoding='utf-8')
        i = kod.find('def test_kurulum_bolumu_SILMEDEN_ONCE_dogrulama_cagiriyor')
        assert i >= 0, 'ŞARTIN yazıldığı test kaldırılmış'
        govde = kod[i:kod.find('\n    def ', i + 10)]
        assert r'StrCmp\s+\$R0\s+"1"\s+(\w+)' in govde, (
            'ŞARTIN istediği dallanma-yönü regexi testte yok')
        for parca in ('i_abort', 'i_etiket', 'i_strcmp < i_abort < i_etiket'):
            assert parca in govde, f'ŞART iddiasının {parca} ayağı yok'

    def test_mutasyon_kanidi_kayitli(self):
        yol = KANIT / 'mutasyon.json'
        assert kanit_gerekli(yol).exists(), 'mutasyon kanıtı yok'
        d = json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))
        kayitlar = {m['ad']: m for m in d['mutasyonlar']}
        onc = kayitlar['M2a_nsi_1_to_0_SART_SOKULU']
        son = kayitlar['M2b_nsi_1_to_0']
        assert onc['kirmizi'] is False, (
            'ŞART öncesi mutasyonun GÖRÜNMEZ olduğu ölçülmemiş — kalemin '
            'gerekçesi kanıtsız')
        assert son['kirmizi'] is True, 'ŞART sonrası mutasyon kırmızı vermiyor'


# ---------------------------------------------------------------------------
# OH-D24-06 — çapa şablonu köprü ucunu çağırmalı
# ---------------------------------------------------------------------------

class TestOHD2406CapaKopruUcu:

    @staticmethod
    def _sablon():
        return kanit_gerekli(CAPA_SABLONU).read_text(encoding='utf-8')

    @staticmethod
    def _kopru_blogu(s):
        """Şablonun köprü bölümü — YORUM DEĞİL, çalışan kod dilimi.

        İlk yazımda bekçi yalnız `'/api/fea/structural' in s` diyordu ve
        bloğun tamamı sökülünce YEŞİL kalıyordu: adres modül başlığındaki
        açıklamada da geçiyor (M3 mutasyonu bunu yakaladı). Artık ÇAĞRI
        ifadesi aranır.
        """
        i = s.find('# --- B9..B11) TÜRETİMLİ KÖPRÜ UCU')
        return s[i:s.find("out['B_paket_uclari'] = B", i)] if i >= 0 else ''

    def test_kopru_ucu_CAGRILIYOR(self):
        s = self._sablon()
        assert "_cagir_fea('/api/fea/structural'" in s, (
            'PK6 çapa şablonu FEA köprü ucunu hiç ÇAĞIRMIYOR — köprünün '
            'hüküm değişiklikleri (D19`da 28,29 -> 39,68) çapada görünmez '
            '(OH-D24-06). Adresin yorumda geçmesi çağrı değildir.')
        assert self._kopru_blogu(s), 'köprü bölümü sökülmüş'

    def test_UC_motorun_da_hukmu_capada(self):
        blok = self._kopru_blogu(self._sablon())
        for ad in ('A1_hibrit_calculate', 'A2_kati_calculate_solid',
                   'A3_sivi_calculate_liquid'):
            assert ad in blok, f'{ad} köprüye verilmiyor'
        assert '_A_GOVDELERI' in blok, (
            'köprü çağrısı TÜRETİMLİ değil — motor sonucu A bölümünden '
            'gelmiyorsa zincir kopuk, sabit yük çapayı yalancı yapar')

    def test_hukum_ozeti_sarmalin_ICINE_bakiyor(self):
        """Uç `{'status','fea':{...}}` döner; özet dışarıdan okunursa BOŞ."""
        s = self._sablon()
        assert "j.get('fea')" in s, (
            'hüküm özeti `fea` sarmalına inmiyor — özet sessizce boşalır '
            '(ilk koşumda üç uçta da hukum={} ölçüldü)')

    @pytest.mark.parametrize('dosya', ['capa_taban.json', 'capa.json'])
    def test_capa_kaydi_kopru_hukmunu_TASIYOR(self, dosya):
        yol = KANIT / dosya
        assert kanit_gerekli(yol).exists(), f'{dosya} yok'
        d = json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))
        B = d['B_paket_uclari']
        uclar = [k for k in B if k.startswith(('B9_fea', 'B10_fea', 'B11_fea'))]
        assert len(uclar) == 3, f'üç köprü ucu bekleniyordu, {uclar}'
        for k in uclar:
            kayit = B[k]
            assert kayit['durum'] == 200, f'{k} 200 dönmedi'
            assert len(kayit['sha256']) == 64
            h = kayit['hukum']
            assert h and h.get('status') == 'ok', f'{k} hüküm özeti boş'
            assert 'min_safety_factor' in (h.get('scalars') or {}), (
                f'{k} emniyet katsayısı çapada yok — kalemin adıyla '
                'saydığı hüküm (28,29 -> 39,68) yine görünmez')
            assert 'converged' in (h.get('meta_hukum') or {}), (
                f'{k} yakınsama hükmü çapada yok')

    def test_capa_BIT_AYNI(self):
        """Bu kulvar ürün koduna dokunmadı; 14 ucun 14`ü aynı olmalı."""
        a = json.loads((kanit_gerekli(KANIT / 'capa_taban.json')).read_text(encoding='utf-8'))
        b = json.loads((kanit_gerekli(KANIT / 'capa.json')).read_text(encoding='utf-8'))
        farklar = []
        for bolum in a:
            for k in a[bolum]:
                if a[bolum][k].get('sha256') != b[bolum].get(k, {}).get('sha256'):
                    farklar.append(f'{bolum}/{k}')
        assert not farklar, f'beyansız çapa farkı: {farklar}'
