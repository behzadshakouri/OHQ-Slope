from pathlib import Path
import tempfile
import unittest

from backend.workflow import execute
from hydrology.column import DEFAULT, initial_pressure, map_pressure, ready, reference_depths, simulate, validate_column
from validation.cell_centred import profile_difference
from validation.ponding import SPEC, FAILURE_DEPTH, differences, hydrostatic_surface_depth, initial_pressure as reference_initial, reference, retention
from test_hydrology import column_request


class FormulationTests(unittest.TestCase):
    def test_old_requests_keep_legacy_convention(self):
        old={key:value for key,value in DEFAULT.items() if key!='formulation'}
        normalized=validate_column(old,1)
        self.assertEqual(normalized['formulation'],'legacy_top')
        self.assertEqual(reference_depths(normalized)[0],0)

    def test_centre_mapping_and_supported_depth_interval(self):
        spec={**DEFAULT,'formulation':'cell_centred'}
        depths=reference_depths(spec)
        self.assertAlmostEqual(depths[0],.0625)
        self.assertAlmostEqual(depths[-1],1.9375)
        with self.assertRaises(ValueError):validate_column(spec,.01)
        with self.assertRaises(ValueError):validate_column(spec,1.95)
        with self.assertRaises(ValueError):validate_column({**spec,'formulation':'unknown'},1)
        self.assertEqual(validate_column(spec,1.9)['formulation'],'cell_centred')
        self.assertEqual(validate_column({**spec,'cells':64},1)['cells'],64)
        with self.assertRaises(ValueError):validate_column({**spec,'cells':65},1)
        with self.assertRaises(ValueError):validate_column({**spec,'formulation':'legacy_top','cells':64},1)
        # Hydrostatic H=0.2 gives psi=H+vertical depth at any reference layout.
        self.assertAlmostEqual(map_pressure([.2+d for d in depths],depths,.73),.93)

    def test_near_saturation_initial_state_has_correct_excess_storage(self):
        spec={**SPEC,'initial_theta':.3998}
        pressure=reference_initial(spec)
        self.assertAlmostEqual(retention(pressure,spec)[0],spec['initial_theta'],places=13)
        self.assertAlmostEqual(pressure,initial_pressure(spec),places=13)


@unittest.skipUnless(ready(),'Build pinned OHQ console for the cell-centred component checks.')
class CellCentredTests(unittest.TestCase):
    def test_independent_profiles_water_balance_and_drainage(self):
        with tempfile.TemporaryDirectory() as temp:
            for base in ('sealed','unit_gradient'):
                with self.subTest(base=base):
                    spec={**SPEC,'formulation':'cell_centred','cells':16,'base':base,'solver_step_h':1/240}
                    ohq=simulate(Path(temp)/base,spec,FAILURE_DEPTH)
                    ref=reference(16,spec['solver_step_h']/24,spec=spec)
                    self.assertLess(differences(ohq,ref)['maximum_failure_pressure_difference_m'],.0005)
                    self.assertLess(profile_difference(ohq,ref),.0005)
                    self.assertLess(ohq['water_balance_max_residual_m3'],1e-8)
                    self.assertGreaterEqual(ohq['minimum_surface_storage_m3'],-1e-10)
                    self.assertAlmostEqual(ohq['profiles'][-1]['drainage_m3'],ref['profiles'][-1]['drainage_m3'],places=5)
                    if base=='sealed':
                        self.assertAlmostEqual(ohq['profiles'][-1]['surface_storage_m3'],hydrostatic_surface_depth(),places=6)

    def test_near_saturated_dry_start_and_json_fs_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            spec={**SPEC,'formulation':'cell_centred','initial_theta':.3998,'cells':8,
                  'rainfall_mm_h':0,'rain_duration_h':0,'duration_h':1,'solver_step_h':1/240}
            ohq=simulate(Path(temp)/'near-saturation',spec,FAILURE_DEPTH)
            ref=reference(8,spec['solver_step_h']/24,spec=spec)
            self.assertLess(differences(ohq,ref)['maximum_failure_pressure_difference_m'],.001)
            request=column_request();request['column']={**SPEC,'formulation':'cell_centred','duration_h':1,'rain_duration_h':1}
            request['parameters']['failure_depth_m']={'value':.25,'min':.25,'max':.25}
            request['stability_engine']='ohq_json'
            result=execute(request,Path(temp)/'workflow')
            self.assertEqual(result['hydrology']['formulation'],'cell_centred')
            self.assertTrue(result['stability_diagnostic']['python_reference_checked'])
            self.assertIn('cell-centre',result['hydrology']['pressure_mapping'])

    def test_paired_hydraulic_sampling_keeps_selected_formulation(self):
        from test_coupled import request as coupled_request
        request=coupled_request();request['samples']=2
        request['column']={**SPEC,'formulation':'cell_centred','duration_h':1,'rain_duration_h':1}
        request['parameters']['failure_depth_m']={'value':.25,'min':.25,'max':.25}
        with tempfile.TemporaryDirectory() as temp:result=execute(request,Path(temp))
        self.assertEqual(result['hydrology']['formulation'],'cell_centred')
        self.assertTrue(result['hydraulic_uncertainty_sampled'])
        self.assertNotEqual(result['realizations'][0]['hydraulic'],result['realizations'][1]['hydraulic'])


if __name__=='__main__':unittest.main()
