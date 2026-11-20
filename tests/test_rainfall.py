import copy
import csv
from pathlib import Path
import tempfile
import unittest

from backend.workflow import validate_request
from hydrology.column import DEFAULT, render, simulate, validate_column, parse_raw, ready
from hydrology.rainfall import intervals, cumulative_depth_m
from test_hydrology import column_request


SCHEDULE=[{'start_h':.137,'end_h':.413,'intensity_mm_h':35},
          {'start_h':.413,'end_h':.727,'intensity_mm_h':80},
          {'start_h':.911,'end_h':1.199,'intensity_mm_h':20},
          {'start_h':1.337,'end_h':1.5,'intensity_mm_h':50}]
SPEC={**DEFAULT,'depth_m':.5,'cells':8,'duration_h':1.5,'rain_duration_h':0,'rainfall_mm_h':0,
      'output_interval_h':.05,'solver_step_h':1/240,'rainfall_schedule':SCHEDULE}


def exact_depth(t):
    # Independent explicit integrals, not the production helper or rendered bins.
    return (.035*max(0,min(t,.413)-.137)+.080*max(0,min(t,.727)-.413)
            +.020*max(0,min(t,1.199)-.911)+.050*max(0,min(t,1.5)-1.337))


class RainfallTests(unittest.TestCase):
    def test_schedule_normalization_without_mutating_request(self):
        request=column_request();request['column']=copy.deepcopy(SPEC)
        del request['column']['rain_duration_h'];del request['column']['rainfall_mm_h']
        request['parameters']['failure_depth_m'].update(value=.25,min=.25,max=.25)
        before=copy.deepcopy(request)
        normalized=validate_request(request)['column']
        self.assertEqual(normalized['rain_duration_h'],0)
        self.assertEqual(normalized['rainfall_schedule'],SCHEDULE)
        self.assertEqual(request,before)
        normalized['rainfall_schedule'][0]['start_h']=0
        self.assertEqual(request,before)

    def test_integral_and_native_interval_depths(self):
        spec=validate_column(SPEC,.25)
        for t in (0,.137,.3,.413,.727,.85,1.1,1.199,1.4,1.5):
            self.assertAlmostEqual(cumulative_depth_m(spec,t),exact_depth(t))
        with tempfile.TemporaryDirectory() as temp:
            render(temp,spec)
            with (Path(temp)/'rainfall.csv').open() as stream:rows=[list(map(float,r)) for r in csv.reader(stream)]
            self.assertEqual(len(rows),7)
            self.assertAlmostEqual(sum(row[2] for row in rows),.04869)
            for (a,b,rate),(start,end,depth) in zip(intervals(spec),rows):
                self.assertAlmostEqual(start*24,a);self.assertAlmostEqual(end*24,b)
                self.assertAlmostEqual(depth,rate*(b-a)/1000)

    def test_empty_schedule_and_legacy_single_pulse(self):
        dry=validate_column({**SPEC,'rainfall_schedule':[]},.25)
        self.assertEqual(intervals(dry),[(0.,1.5,0.)])
        self.assertEqual(cumulative_depth_m(dry,1.5),0)
        self.assertNotIn('rainfall_schedule',validate_column(DEFAULT,1))
        self.assertAlmostEqual(cumulative_depth_m(DEFAULT,24),.24)
        single={**SPEC,'rainfall_schedule':[{'start_h':0,'end_h':1,'intensity_mm_h':40}]}
        old={k:v for k,v in SPEC.items() if k!='rainfall_schedule'}
        old.update(rain_duration_h=1,rainfall_mm_h=40)
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            render(a,single);render(b,old)
            self.assertEqual((Path(a)/'rainfall.csv').read_bytes(),(Path(b)/'rainfall.csv').read_bytes())

    def test_reject_invalid_or_ambiguous_schedules(self):
        invalid=[None,{},[{}],SCHEDULE[::-1],SCHEDULE*26,
                 [{'start_h':0,'end_h':2,'intensity_mm_h':40}],
                 [{'start_h':.2,'end_h':.2,'intensity_mm_h':40}],
                 [{'start_h':0,'end_h':.3,'intensity_mm_h':201}],
                 [{'start_h':0,'end_h':.3,'intensity_mm_h':True}],
                 [{'start_h':0,'end_h':float('nan'),'intensity_mm_h':40}],
                 [{'start_h':0,'end_h':.5,'intensity_mm_h':40},{'start_h':.4,'end_h':1,'intensity_mm_h':40}]]
        for schedule in invalid:
            with self.subTest(schedule=schedule):
                with self.assertRaises(ValueError):validate_column({**SPEC,'rainfall_schedule':schedule},.25)
        for field in ('rainfall_mm_h','rain_duration_h'):
            with self.assertRaisesRegex(ValueError,'single pulse'):validate_column({**SPEC,field:1},.25)


@unittest.skipUnless(ready(),'Build pinned OHQ console for native schedule tests.')
class NativeRainfallTests(unittest.TestCase):
    def test_events_and_mass_at_every_native_output_for_both_formulations(self):
        for formulation in ('legacy_top','cell_centred'):
            with self.subTest(formulation=formulation),tempfile.TemporaryDirectory() as temp:
                result=simulate(temp,{**SPEC,'formulation':formulation},.25)
                raw=parse_raw(Path(temp)/'raw_observations.txt')
                # Skip the native time-zero placeholders; all subsequent states
                # must satisfy an independently integrated forcing history.
                for j,(t,surface) in enumerate(raw['surface_storage'][1:],start=1):
                    total=surface+raw['drainage_storage'][j][1]+sum(raw[f'storage_{i}'][j][1] for i in range(8))
                    self.assertAlmostEqual(total,.15+exact_depth(t),delta=1e-8)
                self.assertAlmostEqual(result['rainfall_total_m'],.04869)
                self.assertLess(result['water_balance_max_residual_m3'],1e-8)


if __name__=='__main__':unittest.main()
