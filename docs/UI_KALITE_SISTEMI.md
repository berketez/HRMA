# UI kalite sistemi — HRMA'nın dışına taşındı

Bu belge artık burada tutulmuyor. Sistem HRMA'ya ait değil; **bütün projeler için**
bağımsız bir proje olarak yaşıyor ve HRMA onun yalnızca ilk müşterisi.

| Ne | Nerede |
|---|---|
| Proje ve yol haritası | `~/goz/PROJE.md` |
| Teknik tasarım (arayüz denetimi + kumanda) | `~/goz/TASARIM_UI.md` |
| Kumanda göstergesi (ekran çerçevesi) | `~/goz/kumanda_gostergesi.py` |
| Proje kartı | `~/.claude/project-cards/goz.md` |
| Hafıza | `~/.claude/projects/-Users-apple-goz/memory/` |

**HRMA'yı ilgilendiren kısım:** sistemin bulduğu kusurlar normal akıştan geçer —
`docs/BULGU_KAYIT_DEFTERI.md`'ye kalem düşer. Sistemin kendi kodu HRMA ağacına girmez,
bu yüzden 2.6.27 yayınını etkilemez. HRMA'nın mevcut `tools/browser_harness/` turu
korunur ve sisteme **alan eklentisi** olarak bağlanır (rozet rengi ↔ fizik hükmü gibi
alana özgü denetimleri hiçbir genel araç yapamaz).
