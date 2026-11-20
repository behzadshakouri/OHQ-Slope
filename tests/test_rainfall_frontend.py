from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'),'Node required for browser input parser unit check.')
class RainfallParserTests(unittest.TestCase):
    def test_schedule_text_parses_without_silent_blank_values(self):
        source=(Path(__file__).resolve().parents[1]/'frontend/app.js').read_text()
        function=source[source.index('function parseRainfallSchedule('):source.index('function rainfallChanged(')]
        script=function+'''
const assert=require('node:assert/strict');
assert.deepEqual(parseRainfallSchedule(''),[]);
assert.deepEqual(parseRainfallSchedule(' .5, 1, 40\\n1.5 2 0 '),[
 {start_h:.5,end_h:1,intensity_mm_h:40},{start_h:1.5,end_h:2,intensity_mm_h:0}]);
for(const text of ['0, 1,',',1,40','0,,1,40','0,1,NaN','0 1','0,1,40\\n\\n2,3,40'])
 assert.throws(()=>parseRainfallSchedule(text),/Rain row/);
'''
        result=subprocess.run(['node','-e',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
