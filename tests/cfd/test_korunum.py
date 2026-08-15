# tests/cfd — korunum bütçesi bekçisi (basamak 4)
"""
Kararlı hâlde giriş-çıkış akı dengeleri: hücre-merkezli FVM korunum
formundadır; iç yüzey akıları teleskopik olarak birebir sadeleşir, duvar
(kayma) yüzeyinde kütle/enerji akısı sıfırdır, eksen yüzeyleri geometrik
akısızdır. Dolayısıyla giriş-çıkış farkı = Σ hücre kalıntısı; derin
yakınsamada makine-hassasiyeti sınıfına inmesi ZORUNLUDUR — inmiyorsa şema
korunum formunu kaybetmiştir (eski cfd_analysis.py'nin ölüm sebebi).

Eşikler ölçümden konuldu (dosya sonundaki sabitlerin yanında ölçüm değeri);
görevin istediği 1e-8 sınıfının altı doğrulandı.

Kaynak terim NOTU: eksenel simetrik basınç kaynağı yalnız r-momentum
denklemindedir; kütle ve enerji bütçesine kaynak girmez, bu yüzden bütçe
kapanışı kaynak teriminden bağımsız bir bekçidir (mutasyon 2'yi debi bekçisi
yakalar, bu dosya değil — bilinçli işbölümü).
"""

import numpy as np

# ÖLÇÜLDÜ (bu depo, M4 Max, 2026-08-15; 120×24, derin yakınsama —
# tol_res=1e-10, settle_tol=1e-11, kalıntı 6,9e-12):
#   kütle bağıl artığı  : 1,14e-11
#   enerji bağıl artığı : 8,76e-12
# Eşik = ölçüm × ~9 payı = tasarım belgesinin "1e-10 sınıfı" hedefi;
# görevin 1e-8 sınıfının 100 katı altında (gevşetme yok).
KUTLE_ARTIK_TOL = 1e-10
ENERJI_ARTIK_TOL = 1e-10


def test_kutle_akisi_dengesi(lule_cozumu):
    _, res = lule_cozumu
    assert res['converged'] is True, 'bütçe hükmü yakınsamış çözüm ister'
    rel = res['mass_balance_rel']
    assert rel < KUTLE_ARTIK_TOL, (
        f'kütle bütçesi kapanmadı: |mdot_in − mdot_out|/mdot_in = {rel:.3e} '
        f'>= {KUTLE_ARTIK_TOL:.0e} — FVM korunum formu bozulmuş')


def test_enerji_akisi_dengesi(lule_cozumu):
    _, res = lule_cozumu
    rel = res['energy_balance_rel']
    assert rel < ENERJI_ARTIK_TOL, (
        f'enerji bütçesi kapanmadı: bağıl artık {rel:.3e} >= '
        f'{ENERJI_ARTIK_TOL:.0e} (duvar akısı sızıntısı ya da korunum '
        f'formu kaybı)')


def test_butce_beyani_alanlari(lule_cozumu):
    """Korunum bütçesi çıktıda BEYAN edilir (dürüstlük sözleşmesi):
    sayılar sonuç sözlüğünde, tüketici gizli hesaba muhtaç değil."""
    _, res = lule_cozumu
    for key in ('mass_flow_in_kg_s', 'mass_flow_out_kg_s',
                'mass_balance_rel', 'energy_flux_in_W', 'energy_flux_out_W',
                'energy_balance_rel'):
        assert key in res, f'korunum bütçesi beyanı eksik: {key}'
        assert np.isfinite(res[key])
    assert res['mass_flow_in_kg_s'] > 0.0
    assert res['energy_flux_in_W'] > 0.0
