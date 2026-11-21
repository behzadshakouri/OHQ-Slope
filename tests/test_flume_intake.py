import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from validation.flume_intake import evaluate_holdout, normalize


class FlumeIntakeTests(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.folder = Path(self.scratch.name)
        self.scenario = json.loads((Path(__file__).resolve().parents[1]/
                                    'models/seepage_2d_example.json').read_text())
        self.metadata = {
            'event_id':'synthetic','clock_origin':'rain logger zero',
            'rain_time_unit':'s','pressure_time_unit':'s','rain_offset_h':0,
            'pressure_offset_h':30/3600,'rain_unit':'mm/min','pressure_unit':'kPa',
            'pressure_reference':'suction_positive','water_unit_weight_kn_m3':9.807,
            'coordinate_tolerance_m':.005,'calibration':{
                'material':'soil','min_ksat_m_day':.2,'max_ksat_m_day':2,'samples':240,'burn_in':60},
        }
        self.rain = self.folder/'rain.csv'
        self.pressure = self.folder/'pressure.csv'
        self.sensors = self.folder/'sensors.csv'
        self.rain.write_text('start,end,intensity\n0,120,0\n120,300,1\n300,450,0\n')
        self.pressure.write_text('sensor_id,time,value\nA,0,1.9614\nB,0,.9807\nA,120,.9807\nB,120,.49035\n')
        self.sensors.write_text('sensor_id,role,x_m,elevation_m,column,layer,sigma_m\n'
                                'A,calibration,.05,.24375,0,1,.01\nB,holdout,.35,.13125,3,1,.01\n')

    def result(self):
        return normalize(self.scenario,self.metadata,self.rain,self.pressure,self.sensors)

    def test_units_offsets_and_holdout(self):
        data = self.result()
        self.assertAlmostEqual(data['audit']['rainfall_total_mm'],3.)
        observed, = data['calibration']['observations']
        self.assertAlmostEqual(observed['series'][0]['time_h'],30/3600)
        self.assertAlmostEqual(observed['series'][0]['pressure_head_m'],-.2)
        self.assertEqual(list(data['holdout']),['B'])
        self.assertEqual(data['holdout']['B']['column'],3)

    def test_total_head_uses_each_sensor_datum(self):
        self.metadata.update(pressure_unit='m',pressure_reference='total_head')
        self.pressure.write_text('sensor_id,time,value\nA,0,.3\nA,120,.4\nB,0,.3\nB,120,.4\n')
        data = self.result()
        self.assertTrue(math.isclose(data['holdout']['B']['series'][0]['pressure_head_m'],.3-.13125))

    def test_missing_rainfall_interval_is_rejected(self):
        self.rain.write_text('start,end,intensity\n0,120,0\n150,450,1\n')
        with self.assertRaisesRegex(ValueError,'continuously'):
            self.result()

    def test_wrong_sensor_cell_is_rejected(self):
        self.sensors.write_text(self.sensors.read_text().replace('A,calibration,.05','A,calibration,.15'))
        with self.assertRaisesRegex(ValueError,'outside the assigned cell'):
            self.result()

    def test_repeated_pressure_times_are_rejected(self):
        self.pressure.write_text(self.pressure.read_text().replace('A,120','A,0'))
        with self.assertRaisesRegex(ValueError,'repeated'):
            self.result()


    def test_holdout_bias_and_geometry(self):
        data = self.result()
        probe = data['holdout']['B']
        start,end = (row['time_h'] for row in probe['series'])
        history = [{'time_h':t,'pressure_head_m':[0.,.1]} for t in (start,end)]
        result = {'hydrology':{'x_edges_m':[0.,.1,.2,.3,.4],'cell_height_m':.0375,
                              'surface_elevation_m':[.3,.2625,.225,.1875],
                              'histories':[[],[],[],history]}}
        scores = evaluate_holdout(result,data['holdout'])
        self.assertAlmostEqual(scores['B']['bias_m'],.175)
        result['hydrology']['surface_elevation_m'][3] += .01
        with self.assertRaisesRegex(ValueError,'mesh differs'):
            evaluate_holdout(result,data['holdout'])
