"""ÖH Dalga-19 · kulvar **app-api** · aşama a1 — bekçiler.

Kapsanan defter kalemleri
-------------------------
* **P7B4-09** — ``/api/cfd/nozzle`` çıkış sınır koşulu hakkında ÖLÇÜMÜNE
  AYKIRI beyan basıyordu. Çözücü ``outlet_bc`` bloğunda çıkış kolonundaki
  ses-altı hücreleri sayıyor (``subsonic_cells``), çapasız koşuda kendi
  uyarısını üretiyor (``unanchored_warning``) ve çareyi
  (``outlet_subsonic_anchor='core_pressure'``) söylüyordu; uç bu bloğu HİÇ
  okumuyor, yalnız ``Pb`` alanının gönderilip gönderilmediğine bakan el
  yazısı bir cümleyle "That is the correct treatment for a **fully
  supersonic exit**" yayımlıyordu. ÖLÇÜLDÜ (``once_a1.json``, taban
  ``60cd341``): 5/12 hücre ses-altı (Mach_min 0,8887) iken iddia basılıyor,
  ``outlet_bc`` / ``subsonic_cells`` / ``ÇAPASIZ`` / ``core_pressure``
  dördü de yanıtta YOK.

* **P7B3-30** — termal FEA zincirinin iki ucu FARKLI malzeme kullanıyordu.
  ``/api/analysis/wall-profile`` ``material`` gönderilmediğinde sessizce
  ``'steel'``e düşüyor ve bunu ``inputs_assumed``da SÖYLEMİYORDU; canlı
  zincirde (``thermal_fea_panel.js::buildWallProfileBody``) ``material``
  hiç gönderilmiyor, mesh ise motorun kendi malzemesiyle çözülüyordu.
  ÖLÇÜLDÜ (aynı motor, değişen tek şey ``material``): ``q_MW`` tepe
  6,122 (graphite) ⟷ 24,009 (steel) ⟷ 25,251 (steel_4130) MW/m², oran
  **4,125**.

* **P13B1-02** (ŞART, ikinci ayak) — ``/api/update/open-download`` gövdesi
  tabanda hiç çalıştırılmamıştı (yan etkili: sistem tarayıcısını açar).
  Burada ``webbrowser.open`` monkeypatch'iyle YAN ETKİSİZ koşuluyor.

Ölçüm yöntemi: port bağlanmaz, Flask ``test_client``. Hiçbir sayı sabite
çivilenmez; kilitlenen şey sözleşme ve beyanın ÖLÇÜMDEN okunmasıdır.
"""

import contextlib
import io
import json

import pytest

from tests.support.fea_lule import ag_malzemesi


def _quiet(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ===========================================================================
# P7B4-09 — çıkış sınır koşulu beyanı ÖLÇÜMDEN okunur
# ===========================================================================
#: Çapasız vakanın konturu: hazne 50 mm, boğaz 30 mm, çıkış 31 mm (kısa
#: dıraksak) — P07 ``B4-repro-09.py``nin ölçtüğü gövdenin aynısı.
CAPASIZ_GAZ = {'P0_Pa': 2.0e6, 'T0_K': 3000.0, 'gamma': 1.2,
               'R_J_per_kgK': 350.0, 'P_ambient_Pa': 20000.0}


@pytest.fixture(scope='module')
def capasiz_kontur():
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    pts, _ = _quiet(sample_nozzle_inner_contour, {
        'chamber_diameter': 0.050, 'throat_diameter': 0.030,
        'exit_diameter': 0.031,
        'nozzle_angles': {'nozzle_type': 'conical',
                          'convergent_half_angle_deg': 30,
                          'divergent_half_angle_deg': 15}})
    return [[float(z) / 1000.0, float(r) / 1000.0] for z, r in pts]


@pytest.fixture(scope='module')
def capasiz_yanit(client, capasiz_kontur):
    resp = _quiet(client.post, '/api/cfd/nozzle',
                  json=dict(CAPASIZ_GAZ,
                            nozzle_contour={'points': capasiz_kontur}))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()


class TestP7B409CikisBeyaniOlcumdenOkunur:
    """Çapasız çıkışta "fully supersonic exit" iddiası KAZANILMAMIŞTIR."""

    def test_cozucunun_outlet_bc_blogu_yanitta(self, capasiz_yanit):
        o = capasiz_yanit['cfd']['outlet_bc']
        for anahtar in ('subsonic_cells', 'cells_total', 'anchored',
                        'unanchored_warning', 'subsonic_anchor', '_basis'):
            assert anahtar in o, f'outlet_bc.{anahtar} düşmüş: {sorted(o)}'

    def test_bu_kosuda_cikis_gercekten_ses_alti(self, capasiz_yanit):
        """Vakanın kendisi hâlâ geçerli mi? (bekçi boşa dönmesin)"""
        o = capasiz_yanit['cfd']['outlet_bc']
        assert o['subsonic_cells'] > 0, (
            'bu kontur artık çapasız vaka üretmiyor; bekçi anlamsızlaştı')
        assert o['anchored'] is False

    def test_uc_tam_supersonik_cikis_iddia_etmez(self, capasiz_yanit):
        cumle = capasiz_yanit['cfd']['inputs']['back_pressure_basis']
        assert 'fully supersonic exit' not in cumle, cumle

    def test_beyan_olculen_sayiyi_tasir(self, capasiz_yanit):
        cfd = capasiz_yanit['cfd']
        cumle = cfd['inputs']['back_pressure_basis']
        o = cfd['outlet_bc']
        assert str(int(o['subsonic_cells'])) in cumle, cumle
        assert 'outlet_bc' in cumle, cumle

    def test_cozucunun_uyarisi_ve_caresi_yanitta(self, capasiz_yanit):
        gov = json.dumps(capasiz_yanit, ensure_ascii=False)
        assert 'ÇAPASIZ' in gov
        assert 'core_pressure' in gov
        assert 'subsonic_cells' in gov

    def test_alan_blogu_beyani_dogruluyor(self, capasiz_yanit):
        """Yanıtın KENDİ alan bloğu ile outlet_bc aynı şeyi söylüyor."""
        cfd = capasiz_yanit['cfd']
        mach_cikis = cfd['field']['mach'][-1]
        olculen = sum(1 for m in mach_cikis if m is not None and m < 1.0)
        assert olculen == cfd['outlet_bc']['subsonic_cells'], (
            f'alan bloğu {olculen}, outlet_bc '
            f"{cfd['outlet_bc']['subsonic_cells']}")


class TestP7B409KunyeYardimcisi:
    """``_cfd_back_pressure_basis`` — iddia yalnız ölçümle kurulur."""

    def test_pb_verilince_cumle_degismedi(self):
        from hrma.app import _cfd_back_pressure_basis
        c = _cfd_back_pressure_basis(1000.0, {'subsonic_cells': 5,
                                              'cells_total': 12})
        assert 'Pb_Pa was supplied' in c
        assert 'fully supersonic' not in c

    def test_sifir_ses_alti_hucrede_iddia_kurulabilir(self):
        from hrma.app import _cfd_back_pressure_basis
        c = _cfd_back_pressure_basis(None, {'subsonic_cells': 0,
                                            'cells_total': 12,
                                            'unanchored_warning': None})
        assert 'fully supersonic exit' in c
        assert '0 subsonic cells' in c

    def test_ses_alti_hucre_varsa_iddia_kurulmaz(self):
        from hrma.app import _cfd_back_pressure_basis
        c = _cfd_back_pressure_basis(None, {'subsonic_cells': 5,
                                            'cells_total': 12,
                                            'unanchored_warning': 'ÇAPASIZ x'})
        assert 'fully supersonic exit' not in c
        assert '5/12' in c
        assert 'ÇAPASIZ x' in c

    def test_olcum_yoksa_iddia_kurulmaz(self):
        from hrma.app import _cfd_back_pressure_basis
        for blok in (None, {}, {'subsonic_cells': None},
                     {'subsonic_cells': True}):
            c = _cfd_back_pressure_basis(None, blok)
            assert 'fully supersonic exit' not in c, (blok, c)
            assert 'not measured' in c, (blok, c)


# ===========================================================================
# P7B3-30 — zincirin iki ucu aynı malzemeyi kullanır
# ===========================================================================
WP_GOVDE = {
    'chamber_pressure': 40.0, 'chamber_temperature': 3000.0,
    'chamber_diameter': 0.1, 'chamber_length': 0.5, 'burn_time': 10.0,
    'mdot_total': 1.0, 'throat_diameter': 0.03,
}


def _wall_profile(client, **ek):
    resp = _quiet(client.post, '/api/analysis/wall-profile',
                  json=dict(WP_GOVDE, **ek))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    return resp.get_json()


class TestP7B330MalzemeBeyani:
    """Sessizce ``'steel'``e düşen malzeme ADIYLA ilan edilir."""

    def test_malzemesiz_istek_material_i_beyan_eder(self, client):
        j = _wall_profile(client)
        alanlar = {b['field'] for b in j.get('inputs_assumed', [])}
        assert 'material' in alanlar, j.get('inputs_assumed')

    def test_beyan_dustugu_degeri_ve_gerekcesini_tasir(self, client):
        j = _wall_profile(client)
        b = next(x for x in j['inputs_assumed'] if x['field'] == 'material')
        assert b['assumed_value'] == j['wall_profile']['material']
        assert 'Tw_ref' in b['reason']

    def test_material_gonderilirse_beyan_yok(self, client):
        j = _wall_profile(client, material='steel_4130')
        alanlar = {b['field'] for b in j.get('inputs_assumed', [])}
        assert 'material' not in alanlar, j.get('inputs_assumed')

    def test_malzeme_q_yi_gercekten_oynatiyor(self, client):
        """Beyanın gerekçesi ölçülebilir olmalı (yoksa beyan boş laf)."""
        q = {}
        for mal in ('graphite', 'steel', 'steel_4130'):
            wp = _wall_profile(client, material=mal)['wall_profile']
            sayilar = [x for x in wp['q_MW']
                       if isinstance(x, (int, float))]
            q[mal] = max(sayilar)
        assert q['graphite'] < q['steel'] < q['steel_4130']
        assert max(q.values()) / min(q.values()) > 2.0, q


class TestP7B330ZincirAyniMalzeme:
    """``/api/fea/thermal`` başka malzemenin h(z)'siyle hüküm vermez."""

    HIBRIT = {
        'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
        'chamber_pressure': 20, 'of_ratio': 2.5, 'fuel_type': 'htpb',
        'oxidizer_type': 'n2o', 'expansion_ratio': 4.0,
        'nozzle_type': 'conical', 'chamber_material': 'steel_4130',
        'wall_thickness': 5,
    }
    KUCUK = {'n_axial': 12, 'n_radial': 4, 'max_halvings': 3}

    @pytest.fixture(scope='class')
    def motor(self, client):
        r = _quiet(client.post, '/calculate', json=self.HIBRIT,
                   headers={'Host': '127.0.0.1:8080'})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        return r.get_json()['motor']

    def _profil(self, client, motor, material):
        r = _quiet(client.post, '/api/analysis/wall-profile', json={
            'chamber_pressure': motor['chamber_pressure'],
            'chamber_temperature': motor['chamber_temperature'],
            'chamber_diameter': motor['chamber_diameter'],
            'chamber_length': motor['chamber_length'],
            'burn_time': motor['burn_time'],
            'mdot_total': motor['mdot_total'],
            'throat_diameter': motor['throat_diameter'],
            'exit_diameter': motor['exit_diameter'],
            'expansion_ratio': motor['expansion_ratio'],
            'nozzle_type': 'conical',
            'material': material,
            'wall_thickness': 0.005,
        }, headers={'Host': '127.0.0.1:8080'})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        return r.get_json()['wall_profile']

    def _fea(self, client, motor, profil):
        yuk = dict(self.KUCUK, motor=motor, axial_profile=profil,
                   ambient_temperature_K=293.15)
        r = _quiet(client.post, '/api/fea/thermal', json=yuk,
                   headers={'Host': '127.0.0.1:8080'})
        return r.status_code, r.get_json()

    # V301/PANEL (NK-12) — ROLLER ÇEVRİLDİ, kapı AYNI (gerekçeli): termal
    # alan yalnız lüledir ve ağ motorun LÜLE malzemesiyle (bu motorda
    # grafit) çözülür. "Aynı malzeme" artık grafit, "farklı" kamaranın
    # çeliği; P7B3-30 sözleşmesi (iki uç aynı cidarı anlatır) değişmedi.
    def test_ayni_malzeme_gecer(self, client, motor):
        ag = ag_malzemesi(motor, 'steel_4130')
        assert ag == 'graphite'
        kod, j = self._fea(client, motor, self._profil(client, motor, ag))
        assert kod == 200, str(j)[:400]
        assert j['fea']['status'] == 'ok', str(j['fea'])[:300]
        assert j['fea']['scalars']['material_key'] == ag

    def test_farkli_malzeme_adiyla_reddedilir(self, client, motor):
        kod, j = self._fea(client, motor,
                           self._profil(client, motor, 'steel_4130'))
        assert kod == 422, str(j)[:400]
        assert j['error'] == 'axial_profile_material_mismatch'
        alan = j['invalid_fields'][0]
        assert alan['field'] == 'axial_profile.material'
        assert alan['value'] == 'steel_4130'
        assert alan['expected_material'] == 'graphite'

    def test_redde_hicbir_sicaklik_alani_yayimlanmaz(self, client, motor):
        # V301/PANEL (NK-12): "farklı malzeme" artık kamaranın çeliği
        # (ağ lüle malzemesiyle — grafit — çözülür); kapı aynı.
        kod, j = self._fea(client, motor,
                           self._profil(client, motor, 'steel_4130'))
        assert kod == 422
        gov = json.dumps(j, ensure_ascii=False)
        for yasak in ('peak_wall_T_K', 'temperature_final_K',
                      'material_limits', '"mesh"'):
            assert yasak not in gov, yasak
        # Uydurma malzeme konmadı: red, çözülecek malzemeyi ADIYLA söyler.
        assert j['expected_material'] == 'graphite'


# ===========================================================================
# P13B1-02 (ŞART 2. ayak) — /api/update/open-download gövdesi YAN ETKİSİZ
# ===========================================================================
class TestP13B102AcikIndirmeGovdesi:
    """Uç tabanda hiç ÇALIŞTIRILMAMIŞTI; tarayıcı açılmadan koşulur."""

    def test_govde_calisir_ve_url_dondurur(self, client, monkeypatch):
        import webbrowser

        import hrma.utils.update_checker as uc

        cagrilar = []
        # Ağa çıkılmaz ve tarayıcı AÇILMAZ: iki yan etkinin ikisi de
        # kesilir, geriye ucun KENDİ mantığı kalır.
        monkeypatch.setattr(uc, 'check_for_update', lambda *a, **k: {
            'asset': {'url': 'https://example.invalid/HRMA-test.dmg'},
            'page_url': 'https://example.invalid/releases'})
        monkeypatch.setattr(
            webbrowser, 'open',
            lambda url, *a, **k: (cagrilar.append(url), True)[1])
        r = _quiet(client.post, '/api/update/open-download', json={})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        j = r.get_json()
        assert j['opened'] is True, j
        # Tarayıcı gerçekten bu uçtan açılıyor (kanal canlı) ve açılan adres
        # yanıtta da duruyor — sunucu "açtım" deyip başka yere gitmiyor.
        assert cagrilar == ['https://example.invalid/HRMA-test.dmg'], cagrilar
        assert j['url'] == cagrilar[0], j

    def test_get_metodu_405(self, client):
        r = _quiet(client.get, '/api/update/open-download')
        assert r.status_code == 405
