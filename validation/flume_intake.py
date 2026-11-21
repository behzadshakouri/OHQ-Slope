"""Normalize measured flume records for the OHQ section and an independent sensor holdout."""
import argparse
from collections import defaultdict
from copy import deepcopy
import csv
import hashlib
import json
import math
from pathlib import Path

from hydrology.column import interpolate
from hydrology.rainfall import validate_schedule
from hydrology.section import keys, prepare
from uncertainty.section_mcmc import prepare_calibration


TIME_H = {'s':1/3600,'min':1/60,'h':1.}
RAIN_MM_H = {'mm/h':1.,'mm/min':60.,'m/s':3_600_000.}


def rows(path, fields):
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or sorted(reader.fieldnames) != sorted(fields):
            raise ValueError(f'{path.name} must use the template columns: {", ".join(fields)}.')
        for index,row in enumerate(reader,2):
            if any(not isinstance(value,str) or not value.strip() for value in row.values()):
                raise ValueError(f'{path.name}:{index} has missing or extra values.')
            yield {key:value.strip() for key,value in row.items()}


def finite(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Recorded values must be finite.')
    return result


def normalize(scenario, metadata, rainfall_path, pressure_path, sensors_path):
    keys(metadata, {'event_id','clock_origin','rain_time_unit','pressure_time_unit',
                    'rain_offset_h','pressure_offset_h','rain_unit','pressure_unit',
                    'pressure_reference','water_unit_weight_kn_m3','coordinate_tolerance_m',
                    'calibration'}, 'Intake metadata')
    for field in ('event_id','clock_origin'):
        if not isinstance(metadata[field],str) or not metadata[field].strip():
            raise ValueError(f'Document {field}.')
    reference = metadata['pressure_reference']
    if reference not in ('gauge','suction_positive','total_head'):
        raise ValueError('Choose gauge, suction_positive, or total_head pressure_reference.')
    gamma = finite(metadata['water_unit_weight_kn_m3'])
    tolerance = finite(metadata['coordinate_tolerance_m'])
    if gamma <= 0 or tolerance < 0:
        raise ValueError('Use a positive water unit weight and nonnegative coordinate tolerance.')
    factors = {'kPa':1/gamma,'Pa':1/(1000*gamma),'m':1.}
    if metadata['pressure_unit'] not in factors or (reference == 'total_head' and metadata['pressure_unit'] != 'm'):
        raise ValueError('Use Pa, kPa, or m for pressure. Total head must be in m.')

    def clock(kind, value):
        unit = metadata[kind+'_time_unit']
        if unit not in TIME_H:
            raise ValueError('Time units must be s, min, or h.')
        elapsed = finite(value)*TIME_H[unit]+finite(metadata[kind+'_offset_h'])
        for endpoint in (0.,duration):
            if abs(elapsed-endpoint) <= 1e-12:
                return endpoint
        return round(elapsed,12)

    prepare(scenario)
    duration = scenario['duration_h']
    if metadata['rain_unit'] not in RAIN_MM_H:
        raise ValueError('Rainfall intensity units must be mm/h, mm/min, or m/s.')
    rainfall = validate_schedule([
        {'start_h':clock('rain',r['start']),'end_h':clock('rain',r['end']),
         'intensity_mm_h':finite(r['intensity'])*RAIN_MM_H[metadata['rain_unit']]}
        for r in rows(rainfall_path,('start','end','intensity'))
    ],duration)
    if (not rainfall or rainfall[0]['start_h'] != 0 or abs(rainfall[-1]['end_h']-duration)>1e-10
            or any(abs(a['end_h']-b['start_h'])>1e-10 for a,b in zip(rainfall,rainfall[1:]))):
        raise ValueError('Rainfall must cover the event continuously. Include explicit zero-intensity intervals.')

    measured = deepcopy(scenario)
    for column in measured['columns']:
        column['rainfall'] = rainfall
    dx = scenario['width_m']/len(scenario['columns'])
    dz = scenario['cell_height_m']
    sensors, occupied = {}, set()
    for row in rows(sensors_path,('sensor_id','role','x_m','elevation_m','column','layer','sigma_m')):
        name,role = row['sensor_id'],row['role']
        if name in sensors or role not in ('calibration','holdout'):
            raise ValueError(f'Duplicate sensor or unknown role: {name}.')
        i,j = int(row['column']),int(row['layer'])
        if not 0 <= i < len(scenario['columns']):
            raise ValueError(f'{name}: column outside section.')
        count = len(scenario['columns'][i]['materials'])
        if not 0 <= j < count or (i,j) in occupied:
            raise ValueError(f'{name}: layer outside section or cell shared with another sensor.')
        x,y = finite(row['x_m']),finite(row['elevation_m'])
        if not i*dx <= x <= (i+1)*dx or not (count-j-1)*dz <= y <= (count-j)*dz:
            raise ValueError(f'{name}: declared coordinates are outside the assigned cell.')
        center_x,center_y = (i+.5)*dx,(count-j-.5)*dz
        distance = math.hypot(x-center_x,y-center_y)
        sigma = finite(row['sigma_m'])
        if distance > tolerance or sigma <= 0:
            raise ValueError(f'{name}: sensor-to-cell distance exceeds tolerance or sigma is nonpositive.')
        sensors[name] = {'role':role,'column':i,'layer':j,'x_m':x,'elevation_m':y,
                         'cell_center_m':[center_x,center_y],'cell_center_distance_m':distance,'sigma_m':sigma}
        occupied.add((i,j))

    series = defaultdict(list)
    factor = factors[metadata['pressure_unit']]
    for row in rows(pressure_path,('sensor_id','time','value')):
        name = row['sensor_id']
        if name not in sensors:
            raise ValueError(f'Pressure record names unknown sensor {name}.')
        t = clock('pressure',row['time'])
        if not 0 <= t <= duration or (series[name] and t <= series[name][-1]['time_h']):
            raise ValueError(f'{name}: pressure clock is out of range, repeated, or unordered.')
        head = finite(row['value'])*factor
        if reference == 'suction_positive':
            head = -head
        elif reference == 'total_head':
            head -= sensors[name]['elevation_m']
        series[name].append({'time_h':t,'pressure_head_m':head})

    calibration, holdout = [], {}
    for name, sensor in sensors.items():
        if len(series[name]) < 2:
            raise ValueError(f'{name}: at least two pressure observations are required.')
        if sensor['role'] == 'holdout':
            holdout[name] = {**sensor,'series':series[name]}
        else:
            calibration.append({**{key:sensor[key] for key in ('column','layer','sigma_m')},
                                'series':series[name]})
    if not calibration or not holdout:
        raise ValueError('Declare at least one calibration sensor and one distinct holdout sensor.')
    settings = metadata['calibration']
    keys(settings, {'material','min_ksat_m_day','max_ksat_m_day','samples','burn_in'}, 'Calibration settings')
    settings = {**settings,'observations':calibration}
    prepare_calibration(measured,settings)
    return {'scenario':measured,'calibration':settings,'holdout':holdout,
            'audit':{'metadata':metadata,'sensors':sensors,
                     'rainfall_total_mm':math.fsum((r['end_h']-r['start_h'])*r['intensity_mm_h']
                                                   for r in rainfall),
                     'pressure_counts':{name:len(values) for name,values in series.items()}}}


def evaluate_holdout(result, holdout):
    """Score one forward run at the prespecified held-out sensor cells."""
    hydrology = result['hydrology']
    predictions = {}
    for name, sensor in holdout.items():
        i,j = sensor['column'],sensor['layer']
        dx = hydrology['x_edges_m'][i+1]-hydrology['x_edges_m'][i]
        x = hydrology['x_edges_m'][i]+dx/2
        y = hydrology['surface_elevation_m'][i]-(j+.5)*hydrology['cell_height_m']
        if math.dist((x,y),sensor['cell_center_m']) > 1e-9:
            raise ValueError(f'{name}: forward-run mesh differs from the registered sensor mapping.')
        series = [(frame['time_h'],frame['pressure_head_m'][j]) for frame in hydrology['histories'][i]]
        matched = []
        for row in sensor['series']:
            t = row['time_h']
            if not series[0][0] <= t <= series[-1][0]+1e-12:
                raise ValueError(f'{name}: measurement lies outside the forward-run time coverage.')
            predicted = interpolate(series,t)
            error = predicted-row['pressure_head_m']
            matched.append({'time_h':t,'observed_head_m':row['pressure_head_m'],
                            'predicted_head_m':predicted,'residual_m':error})
        errors = [row['residual_m'] for row in matched]
        predictions[name] = {'n':len(errors),'bias_m':math.fsum(errors)/len(errors),
                             'rmse_m':math.sqrt(math.fsum(e*e for e in errors)/len(errors)),
                             'series':matched}
    return predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluate',nargs=3,type=Path,metavar=('FORWARD_JSON','HOLDOUT_JSON','SCORES_JSON'))
    for name in ('scenario','metadata','rainfall','pressure','sensors','output'):
        parser.add_argument(name,type=Path,nargs='?')
    args = parser.parse_args()
    if args.evaluate:
        if args.scenario is not None:
            parser.error('Use either intake paths or --evaluate.')
        forward,holdout,output = args.evaluate
        scores = evaluate_holdout(json.loads(forward.read_text()),json.loads(holdout.read_text()))
        with output.open('x') as stream:
            stream.write(json.dumps(scores,indent=2,allow_nan=False)+'\n')
        return
    input_names = ('scenario','metadata','rainfall','pressure','sensors')
    paths = {name:getattr(args,name) for name in input_names}
    if any(path is None for path in paths.values()) or args.output is None:
        parser.error('Supply scenario, metadata, rainfall, pressure, sensors, and output.')
    result = normalize(json.loads(args.scenario.read_text()),json.loads(args.metadata.read_text()),
                       args.rainfall,args.pressure,args.sensors)
    result['audit']['sha256'] = {name:hashlib.sha256(path.read_bytes()).hexdigest()
                                 for name,path in paths.items()}
    args.output.mkdir(parents=True,exist_ok=False)
    for name, value in result.items():
        (args.output/f'{name}.json').write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
