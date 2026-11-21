import copy
import math
import struct
import tempfile
from pathlib import Path
import zipfile
import unittest

from hydrology.column import DEFAULT, validate_column
from validation.column_sensitivity import sample_profile, metrics, validate_study_column
from validation.column_comparison import compare
from validation.geostudio_archive import mesh_nodes,graph_location,extract


class ColumnSensitivityTests(unittest.TestCase):
    def test_offline_resolution_does_not_expand_app_limits(self):
        spec = dict(DEFAULT, formulation='cell_centred', cells=256, duration_h=2,
                    rain_duration_h=2, solver_step_h=1/960, output_interval_h=1/60)
        near_surface = spec['depth_m']/256
        validate_study_column(spec, near_surface)
        with self.assertRaises(ValueError):
            validate_column(spec, near_surface)
        for overrides in ({'cells':257}, {'output_interval_h':1/120}, {'solver_step_h':1/1920}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                validate_study_column(dict(spec, **overrides), near_surface)

    def test_archive_comparison_selects_saved_times_without_interpolation(self):
        point = {'id':'p', 'vertical_depth_m':.2}
        series = [{'time_h':i/2, 'pressure_head_m':-i} for i in range(3)]
        trial = {'state':'completed', 'specification':{'cells':16,'solver_step_h':1/240},
                 'extracted':{'p':series}}
        study = {'state':'completed', 'study':{'points':[point]},'trials':[trial]}
        ref = {'points':{'p':{'point':point,'series':[series[0], series[-1]]}}}
        value = compare(study, ref)['archive_comparisons'][0]['points']['p']
        self.assertEqual((value['rmse'], value['samples']), (0, 2))
        ref['points']['p']['series'][1] = {'time_h':.9,'pressure_head_m':-2}
        with self.assertRaises(ValueError):
            compare(study, ref)

    def test_sample_moisture_separately_from_pressure(self):
        hydro={'reference_depths_m':[.1,.3], 'profiles':[{'time_h':0,'pressure_head_m':[1,5],'theta':[.2,.4]}]}
        row=sample_profile(hydro,.2)[0]
        self.assertAlmostEqual(row['theta'],.3)
        self.assertAlmostEqual(row['pressure_head_m'],3)
        with self.assertRaises(ValueError):sample_profile(hydro,.01)

    def test_metrics_require_matching_times_and_known_differences(self):
        a=[{'time_h':0,'theta':.2},{'time_h':1,'theta':.4}]
        b=[{'time_h':0,'theta':.1},{'time_h':1,'theta':.2}]
        r=metrics(a,b,'theta');self.assertAlmostEqual(r['bias'],.15)
        self.assertAlmostEqual(r['rmse'],math.sqrt(.025))
        self.assertAlmostEqual(r['maximum_absolute_difference'],.2)
        b[-1]['time_h']=.9
        with self.assertRaises(ValueError):metrics(a,b,'theta')

    def test_comparison_rejects_changed_physics_points_or_partial_runs(self):
        point={'id':'p','vertical_depth_m':.2}
        series=[{'time_h':0,'theta':.2,'pressure_head_m':-.5},{'time_h':1,'theta':.3,'pressure_head_m':-.1}]
        trial={'state':'completed','specification':{'cells':16,'solver_step_h':1/240,'depth_m':1},'extracted':{'p':series}}
        study={'state':'completed','study':{'points':[point]},'trials':[trial]}
        ref={'points':{'p':{'point':point,'series':series}}}
        self.assertEqual(compare(study,ref)['archive_comparisons'][0]['points']['p']['rmse'],0)
        for bad in ('physics','point','status'):
            a,b=copy.deepcopy(study),copy.deepcopy(ref)
            if bad=='physics':
                second=copy.deepcopy(trial);second['specification'].update(cells=32,depth_m=2);a['trials'].append(second)
            elif bad=='point':b['points']['p']['point']['vertical_depth_m']=.3
            else:a['trials'][0]['state']='failed'
            with self.assertRaises(ValueError):compare(a,b)

    def test_binary_mesh_layout_is_checked(self):
        header=b'ply\nformat binary_little_endian 1.0\nelement version 1\nproperty ushort major\nproperty ushort minor\nelement node 1\nproperty double x\nproperty double y\nproperty double z\nend_header\n'
        data=header+struct.pack('<HHddd',1,0,.4,1.3,0)
        self.assertEqual(mesh_nodes(data),{1:(.4,1.3)})
        with self.assertRaises(ValueError):mesh_nodes(data[:-1])

    def test_archive_pressure_units_and_direct_moisture_are_distinct(self):
        header=b'ply\nformat binary_little_endian 1.0\nelement version 1\nproperty ushort major\nproperty ushort minor\nelement node 1\nproperty double x\nproperty double y\nproperty double z\nend_header\n'
        xml='<Root><ResultGraph><CacheId ID="31" CacheSequenceNumber="12"/><X>Time</X><Y>VolWaterContent</Y></ResultGraph><UsesLocation ID="ResultGraphs-31" Entry="6"/><Location><ID>6</ID><Sources><ID>CutLines-7</ID></Sources></Location><CutLine><ID>7</ID><Points><Point X=".4" Y="1.3"/></Points></CutLine></Root>'
        points=[{'id':'pressure','archive_node':1,'x_m':.4,'y_m':1.3},
                {'id':'moisture','archive_theta_graph':'Run/graph_31_12.csv','x_m':.4,'y_m':1.3}]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'case.gsz'
            def write(last_time):
                with zipfile.ZipFile(path,'w') as z:
                    z.writestr('Run/snapshot.xml',xml)
                    z.writestr('Run/Mesh.ply',header+struct.pack('<HHddd',1,0,.4,1.3,0))
                    z.writestr('Run/time.csv','Step,Time\n0,0\n1,3600\n')
                    z.writestr('Run/000/node.csv','Node,PoreWaterPressure\n1,-9.807\n')
                    z.writestr('Run/001/node.csv','Node,PoreWaterPressure\n1,9.807\n')
                    z.writestr('Run/graph_31_12.csv',f'Undefined,Time,VolWaterContent\n1,0,.2\n2,{last_time},.3\n')
            write(3600);r=extract(path,'Run',points)
            self.assertAlmostEqual(r['pressure']['series'][-1]['pressure_head_m'],1)
            self.assertEqual(r['moisture']['series'][-1]['theta'],.3)
            write(7200)
            with self.assertRaisesRegex(ValueError,'time grid'):extract(path,'Run',points)

    def test_graph_coordinate_resolved_from_ids_not_title(self):
        xml='''<Root><ResultGraph><CacheId ID="31" CacheSequenceNumber="12"/><X>Time</X><Y>VolWaterContent</Y></ResultGraph>
        <UsesLocation ID="ResultGraphs-31" Entry="6"/><Location><ID>6</ID><Sources><ID>CutLines-7</ID></Sources></Location>
        <CutLine><ID>7</ID><Points><Point X=".38" Y="1.31"/></Points></CutLine></Root>'''
        r=graph_location(xml,'Run/graph_31_12.csv')
        self.assertEqual((r['x_m'],r['y_m'],r['quantity']),(.38,1.31,'VolWaterContent'))
        with self.assertRaises(ValueError):graph_location(xml,'Run/graph_32_7.csv')
        with self.assertRaisesRegex(ValueError,'sequence'):graph_location(xml,'Run/graph_31_13.csv')


if __name__=='__main__':unittest.main()
