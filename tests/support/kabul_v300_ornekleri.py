"""V301/KABUL — v3.0.0 ile YAYIMLANMIŞ örnek proje dosyaları (göç kapısı).

``git show v3.0.0:examples/<ad>.hrma`` (etiket v3.0.0 = 9e6068b85) çıktısının
BİREBİR JSON'u; elle değiştirilmedi. Test, CI'nin etiketsiz/sığ klonunda da
koşsun diye depodan değil bu modülden okur. Kullanıcının makinesinde
3.0.0'dan kalan proje tam olarak budur (yayın kapısı 3: eski sürüm
projeleri yeni sürümde açılıp hesaplanır).
"""

V300_ORNEKLERI = {'hybrid': {'app_version': '3.0.0',
            'created_at': '2026-10-14T14:51:51',
            'description': 'Öğretici örnek: N2O/HTPB hibrit motor, 3 kN itki, 10 s yanma, 30 bar '
                           'oda basıncı. Regresyon katsayıları uygulamanın HTPB/N2O varsayılanıdır '
                           '(Doran et al., AIAA 2007-5352). / Educational example: N2O/HTPB hybrid '
                           'motor, 3 kN thrust, 10 s burn, 30 bar chamber pressure. Regression '
                           'coefficients are the application defaults for HTPB/N2O (Doran et al., '
                           'AIAA 2007-5352).',
            'format': 'hrma-project',
            'format_version': 1,
            'inputs': {'fields': {'burn_time': 10.0,
                                  'chamber_diameter_input': 0,
                                  'chamber_material': 'steel_304',
                                  'chamber_pressure': 30.0,
                                  'combustion_type': 'infinite',
                                  'expansion_ratio': 0,
                                  'fuel_density': 920,
                                  'fuel_type': 'htpb',
                                  'hole_diameter_max': 2.0,
                                  'hole_diameter_min': 0.3,
                                  'injector_type': 'showerhead',
                                  'l_star': 1.0,
                                  'motor_description': 'Öğretici örnek: N2O/HTPB hibrit motor, 3 '
                                                       'kN itki, 10 s yanma, 30 bar oda basıncı. '
                                                       'Regresyon katsayıları uygulamanın HTPB/N2O '
                                                       'varsayılanıdır (Doran et al., AIAA '
                                                       '2007-5352). / Educational example: '
                                                       'N2O/HTPB hybrid motor, 3 kN thrust, 10 s '
                                                       'burn, 30 bar chamber pressure. Regression '
                                                       'coefficients are the application defaults '
                                                       'for HTPB/N2O (Doran et al., AIAA '
                                                       '2007-5352).',
                                  'motor_name': 'Example Hybrid N2O-HTPB 3kN',
                                  'nozzle_type': 'conical',
                                  'of_ratio': 7.0,
                                  'oxidizer_density': 785.1,
                                  'oxidizer_phase': 'liquid',
                                  'oxidizer_temp': 293.15,
                                  'oxidizer_type': 'n2o',
                                  'oxidizer_viscosity': 6.816999999999995e-05,
                                  'plate_thickness': 3.0,
                                  'regression_a': 3.68e-05,
                                  'regression_n': 0.555,
                                  'single_pressure': 1.013,
                                  'tank_pressure': 50.5,
                                  'target_velocity': 30,
                                  'thrust': 3000.0},
                       'ui_state': {'analysis_tab': 'single',
                                    'design_tab': 'thrust_time',
                                    'environment_tab': 'single'}},
            'motor_type': 'hybrid',
            'name': 'Example Hybrid N2O-HTPB 3kN',
            'results_summary': {'burn_time_s': 10.0,
                                'chamber_pressure_bar': 30.0,
                                'computed_with_version': '3.0.0',
                                'isp_s': 236.034,
                                'thrust_N': 3000.0,
                                'total_impulse_Ns': 29926.591},
            'updated_at': '2026-10-14T14:51:51'},
 'liquid': {'app_version': '3.0.0',
            'created_at': '2026-07-31T19:25:34',
            'description': 'Öğretici örnek: LOX/RP-1 sıvı motor, 25 kN itki, 70 bar oda basıncı, '
                           'O/F 2.3, gaz jeneratörü çevrimi, rejeneratif soğutma. / Educational '
                           'example: LOX/RP-1 liquid engine, 25 kN thrust, 70 bar chamber '
                           'pressure, O/F 2.3, gas-generator cycle, regenerative cooling.',
            'format': 'hrma-project',
            'format_version': 1,
            'inputs': {'fields': {'chamber_material': 'inconel_718',
                                  'chamber_pressure': 70,
                                  'characteristic_length': 1.2,
                                  'combustion_efficiency': 97,
                                  'contraction_ratio': 4,
                                  'cooling_type': 'regenerative',
                                  'discharge_coefficient': 0.7,
                                  'engine_cycle': 'gas_generator',
                                  'feed_pressure': 105,
                                  'fuel_density': 810,
                                  'fuel_type': 'rp1',
                                  'generator_gas_temp': 900,
                                  'injector_pressure_drop': 20,
                                  'injector_type': 'impinging',
                                  'mixture_ratio': 2.3,
                                  'nozzle_expansion_ratio': 12,
                                  'nozzle_type': 'bell_80',
                                  'of_max': 3.2,
                                  'of_min': 2.0,
                                  'oxidizer_density': 1141,
                                  'oxidizer_type': 'lox',
                                  'safety_factor': 2.5,
                                  'stoichiometric_of': 3.4,
                                  'thrust': 25000,
                                  'turbine_expansion_ratio': 4}},
            'motor_type': 'liquid',
            'name': 'Example Liquid LOX-RP1 25kN',
            'results_summary': {'chamber_pressure_bar': 70.0,
                                'computed_with_version': '3.0.0',
                                'isp_s': 277.449,
                                'isp_vacuum_s': 309.182,
                                'thrust_N': 25000.0},
            'updated_at': '2026-10-14T14:18:22'},
 'solid': {'app_version': '3.0.0',
           'created_at': '2026-07-30T17:01:45',
           'description': 'Öğretici örnek: KNDX (KNO3/dekstroz 65/35) katı motor, 75 mm gövde, 3 '
                          'BATES segmenti, 40 bar tasarım basıncı, L sınıfı. Termokimya ve yanma '
                          'hızı uygulamanın merkezi kataloglarından (propellants_db + Nakka 1999 '
                          'rejim fitleri). / Educational example: KNDX (KNO3/dextrose 65/35) solid '
                          'motor, 75 mm case, 3 BATES segments, 40 bar design pressure, L class. '
                          'Thermochemistry and burn rate come from the application catalogues '
                          '(propellants_db + Nakka 1999 regime fits).',
           'format': 'hrma-project',
           'format_version': 1,
           'inputs': {'fields': {'burn_rate_a': 0.0007876,
                                 'burn_rate_n': 0.688,
                                 'burn_rate_preset': 'kndx',
                                 'cf_efficiency': 0.98,
                                 'chamber_diameter': 75.0,
                                 'chamber_pressure': 40.0,
                                 'char_velocity': 915.9,
                                 'combustion_efficiency': 0.95,
                                 'core_diameter': 32.0,
                                 'density': 1850.0,
                                 'erosion_factor': 0.001,
                                 'flame_temp': 1713.1,
                                 'gamma': 1.122,
                                 'grain_count': 3,
                                 'grain_gap': 2.0,
                                 'grain_length': 360.0,
                                 'grain_type': 'bates',
                                 'inhibit_front': False,
                                 'inhibit_outer': True,
                                 'inhibit_rear': False,
                                 'initial_temp': 298.0,
                                 'kinetic_efficiency': 0.97,
                                 'molecular_weight': 37.51,
                                 'nozzle_efficiency': 0.95,
                                 'outer_diameter': 75.0,
                                 'propellant_name': 'KNDX - Potassium Nitrate/Dextrose 65/35',
                                 'web_thickness': 21.5}},
           'motor_type': 'solid',
           'name': 'Example Solid KNDX BATES 75mm',
           'results_summary': {'burn_time_s': 2.277,
                               'chamber_pressure_bar': 40.0,
                               'computed_with_version': '3.0.0',
                               'isp_s': 125.401,
                               'peak_thrust_N': 1499.272,
                               'total_impulse_Ns': 2959.642},
           'updated_at': '2026-10-14T14:18:18'}}
