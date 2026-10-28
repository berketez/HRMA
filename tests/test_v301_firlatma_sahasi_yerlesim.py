"""v3.0.1 (26 Eki 2026) — Fırlatma Sahası: durum iletisi görünür, uçuş özeti
örtülmez, araç künyesinde ham alan yolu yok (NK-48, NK-69).

Son kullanıcı testi:
- NK-48: uçuş çözüldükten sonra Oynat/Sıfırla/İrtifayı abart/Kamera kapalı
  kaldı ve hiçbir yerde neden söylenmedi. Kök iki katlı: (1) "araç kararsız —
  oynatma kapalı" iletisi yazıldığı karede koşulsuz ``setStatus('')`` ile
  siliniyordu; (2) durum satırı sol panelin EN ALTINDAYDI (uzun künye
  paneli kaydırdığı için görünmüyordu). Kapalı ► düğmesi de etkin gibi
  görünüyordu.
- NK-69 (1440×900, hibrit): sol paneldeki künye ham alan yollarıyla
  (structural_analysis.weight_analysis.total_weight …) paneli ekrandan
  taşırıyordu; sağda "UÇUŞ ÖZETİ" turuncu not kutusunun altında kalıyordu.
  ÖLÇÜLDÜ (Playwright, hibrit örnek, 1440×900 ve 1280×800): düzeltmeden
  sonra sağ panel ⟷ not kutusu kesişmez, apoje ve menzil satırları sağ
  panelin görünür alanında, künyenin ana metninde alan yolu yok.
"""
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
SAYFA = (KOK / 'hrma' / 'templates' / 'launch_site.html').read_text(encoding='utf-8')
DIL = (KOK / 'hrma' / 'static' / 'js' / 'i18n_launch_site.js').read_text(encoding='utf-8')


def test_durum_satiri_uc_dugmesinin_altinda_sag_panelde():
    sag = SAYFA.index('id="ls-right"')
    sol = SAYFA.index('id="ls-left"')
    durum = SAYFA.index('id="ls-status"')
    assert SAYFA.count('id="ls-status"') == 1
    assert durum > sag > sol
    assert durum > SAYFA.index('id="ls-fly"')
    assert durum < SAYFA.index('id="ls-playpause"')


def test_kararsiz_arac_iletisi_silinmez():
    govde = SAYFA[SAYFA.index("el('ls-fly').addEventListener('click'"):]
    govde = govde[:govde.index('// ---- Oynatım kontrolleri ----')]
    assert "if (!unstable) setStatus('');" in govde
    # koşulsuz temizleme kalmadı (yalnız istek öncesi "çözülüyor" ve hata yolları)
    kosulsuz = [m.start() for m in re.finditer(r"\n\s*setStatus\(''\);", govde)]
    assert kosulsuz == []


def test_kapali_oynatma_dugmesi_kapali_gorunur():
    assert re.search(r'\.ls-iconbtn:disabled\s*\{[^}]*opacity', SAYFA)


def test_not_kutusu_tavanli_ve_paylar_boy_degisiminde_olculur():
    blok = SAYFA[SAYFA.index('#ls-notes {'):]
    blok = blok[:blok.index('}')]
    assert 'max-height: 30vh' in blok and 'overflow-y: auto' in blok
    assert 'new ResizeObserver(layoutBottomReserve)' in SAYFA


def test_cozumde_ozet_gorunur_alana_kayar():
    assert "var ozet = el('ls-range');" in SAYFA
    assert "ozet.scrollIntoView({ block: 'nearest' })" in SAYFA


def test_dayanak_kuyrugu_acilir_bolumde():
    assert "inertNote.indexOf('; basis: ')" in SAYFA
    assert "det.className = 'ls-basis';" in SAYFA
    assert "t('site.dryMassBasis', 'Dry-mass basis')" in SAYFA
    assert DIL.count("'site.dryMassBasis':") == 2
