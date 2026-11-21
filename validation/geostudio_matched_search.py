"""Compare archived SEEP/W and OHQ pressure fields on identical Bishop slices."""
import argparse
import csv
from itertools import product
import json
import math
from pathlib import Path
from zipfile import ZipFile

from hydrology.column import interpolate
from stability.section import circle_parameters, circular_slices, evaluate_slice_pressures, fixed_surface_history
from validation.geostudio_fixed_slip import digest
from validation.geostudio_pressure_field import SavedPressureField


def write_csv(folder, name, columns, rows):
    with (folder/name).open('w',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def compare(archive_path, native_path, baseline_path, folder):
    baseline = json.loads(baseline_path.read_text())
    native = json.loads(native_path.read_text())
    source = baseline['runs'][native_path.stem]
    if digest(archive_path) != baseline['archive_sha256'] or digest(native_path) != source['input_sha256']:
        raise ValueError('Input archive or native model differs from the fixed-slip benchmark.')
    with ZipFile(archive_path) as archive:
        field = SavedPressureField(archive)
    errors = []
    for (x,y), part in zip(baseline['slice_base_points_m'],baseline['slices'],strict=True):
        history = field.pressure_history(x,y)
        archived = interpolate([(r['time_h'],r['pressure_kpa']) for r in history],baseline['time_h'])
        errors.append(abs(archived-part['pressure_kpa']))
    if max(errors) > 1e-6:
        raise ValueError('Archive interpolation does not reproduce the saved slip pressures.')

    ground = [tuple(point) for point in native['inputs']['archive_geometry']['polygon_m'][1:-1]]
    weight = baseline['screening']['unit_weight_kn_m3']
    material = baseline['slices'][0]
    strength = (material['cohesion_kpa'],material['friction_rad'],material['suction_friction_rad'])
    gamma = native['inputs']['head_conversion_kn_m3']
    candidates = [tuple(trial['candidate']) for trial in baseline['screening']['runs'][native_path.stem]['60']['accepted']]
    circle_ids = {candidate:f'C{i:02d}' for i,candidate in enumerate(candidates,1)}
    times = [t for t,_ in field.frames]
    slice_csv, pressure_csv, fos_csv, circles_csv, arc_csv = [], [], [], [], []

    def evaluate(candidate, count):
        slices, points = circular_slices(ground,*candidate,count,weight,*strength)
        archived = evaluate_slice_pressures(slices,[field.pressure_history(*pt) for pt in points])
        ohq = fixed_surface_history(native['native'],slices,points,gamma)
        if [r['time_h'] for r in archived] != times:
            raise ValueError('Archive frame times changed during evaluation.')
        series = [[(r['time_h'],r['pressure_kpa'][i]) for r in ohq] for i in range(count)]
        for frame in archived:
            pressures = [interpolate(values,frame['time_h']) for values in series]
            frame['ohq_pressure_kpa'] = pressures
        matched = evaluate_slice_pressures(slices, [
            [{'time_h':r['time_h'],'pressure_kpa':r['ohq_pressure_kpa'][i]} for r in archived]
            for i in range(count)
        ])
        return slices,points,archived,matched

    def store(candidate, count, result):
        trial = circle_ids[candidate]
        slices,points,archived,ohq = result
        slice_csv.extend((trial,count,i+1,*xy,s.width_m,s.weight_kn_m,math.degrees(s.downslope_angle_rad))
                         for i,(s,xy) in enumerate(zip(slices,points,strict=True)))
        for a,b in zip(archived,ohq,strict=True):
            t = a['time_h']
            fos_csv.append((trial,count,t,a['factor_of_safety'],b['factor_of_safety']))
            pressure_csv.extend((trial,count,t,i+1,pa,pb) for i,(pa,pb) in
                                enumerate(zip(a['pressure_kpa'],b['pressure_kpa'],strict=True)))

    def search(requested, count, cache=None):
        accepted, rejected = {}, []
        for candidate in requested:
            try:
                result = cache[candidate] if cache is not None and candidate in cache else evaluate(candidate,count)
            except ValueError as error:
                rejected.append({'candidate':candidate,'reason':str(error)})
                continue
            accepted[candidate] = result
        if not accepted:
            raise ValueError('No candidate circles available in both seepage fields.')
        envelopes = []
        for j,t in enumerate(times):
            frame = {'time_h':t}
            for index,name in [(2,'archived_pressure'),(3,'ohq_pressure')]:
                critical = min(accepted,key=lambda trial:accepted[trial][index][j]['factor_of_safety'])
                frame[name] = {'candidate':critical,'fs':accepted[critical][index][j]['factor_of_safety']}
            envelopes.append(frame)
        return accepted,{'accepted':list(accepted),'rejected':rejected,'envelope':envelopes}

    first = {}
    for count in (30,60,120):
        accepted, summary = search(candidates,count)
        first[str(count)] = summary
        if len(accepted) != len(candidates):
            raise ValueError(f'An original circle cannot be evaluated with {count} slices.')
        for candidate,result in accepted.items():
            store(candidate,count,result)
        if count == 60:
            cache = accepted
    expansion = sorted(set(candidates) | set(product(
        [.075,.1,.175,.25,.325,.4,.45],[1.625,1.65,1.725,1.8,1.875,1.95,1.975],[.3,.35,.4,.45,.5])))
    expanded_results, expanded = search(expansion,60,cache)
    finalists = sorted({frame[key]['candidate'] for frame in expanded['envelope']
                        for key in ('archived_pressure','ohq_pressure')} - set(candidates))
    for i,candidate in enumerate(finalists,1):
        circle_ids[candidate] = f'X{i:02d}'
        for count in (30,60,120):
            try:
                result = expanded_results[candidate] if count == 60 else evaluate(candidate,count)
            except ValueError as error:
                raise ValueError(f'Expanded finalist {candidate} failed at {count} slices.') from error
            store(candidate,count,result)
    for candidate in circle_ids:
        entry,exit,sagitta = candidate
        cx,cy,radius = circle_parameters(ground,*candidate)
        circles_csv.append((circle_ids[candidate],entry,interpolate(ground,entry),
                            exit,interpolate(ground,exit),sagitta,cx,cy,radius))
        span = exit-entry
        entry_y,exit_y = interpolate(ground,entry),interpolate(ground,exit)
        leads = [(entry-span/240,entry_y-(entry-cx)/(cy-entry_y)*span/240)]
        arc = [(x,cy-math.sqrt(max(0.,radius**2-(x-cx)**2)))
               for x in (entry+span*i/240 for i in range(241))]
        leads.extend(arc)
        leads.append((exit+span/240,exit_y+(exit-cx)/(cy-exit_y)*span/240))
        arc_csv.extend((circle_ids[candidate],i+1,x,y) for i,(x,y) in enumerate(leads))
    folder.mkdir(parents=True,exist_ok=True)
    write_csv(folder,'circles.csv','circle_id entry_x_m entry_y_m exit_x_m exit_y_m sagitta_m center_x_m center_y_m radius_m'.split(),circles_csv)
    write_csv(folder,'arc_points.csv','circle_id point_no x_m y_m'.split(),arc_csv)
    write_csv(folder,'slices.csv','circle_id count slice_no x_m base_y_m width_m weight_kn_per_m downslope_angle_deg'.split(),slice_csv)
    write_csv(folder,'slice_pressures.csv','circle_id count time_h slice_no archived_pressure_kpa ohq_pressure_kpa'.split(),pressure_csv)
    write_csv(folder,'bishop_fs.csv','circle_id count time_h bishop_with_archived_pressure bishop_with_ohq_pressure'.split(),fos_csv)
    write_csv(folder,'geostudio_fs_template.csv','circle_id count time_h geostudio_fs'.split(),
              ((circle,60,t,'') for circle in circle_ids.values() for t in times))
    write_csv(folder,'geostudio_slice_template.csv',
              'circle_id count time_h slice_no x_m base_y_m width_m weight_kn_per_m downslope_angle_deg pressure_kpa'.split(),
              ((circle,60,t,i,'','','','','','') for circle in circle_ids.values()
               for t in times for i in range(1,61)))
    output = {'archive_sha256':baseline['archive_sha256'],'native_sha256':source['input_sha256'],
              'archive_slip_44_pressure_replay_max_error_kpa':max(errors),
              'unit_weight_kn_m3':weight,'cohesion_kpa':strength[0],
              'friction_deg':math.degrees(strength[1]),'suction_friction_deg':math.degrees(strength[2]),
              'matched_critical_by_slice_count':first,'expanded_critical':expanded,
              'circle_ids':{name:candidate for candidate,name in circle_ids.items()}}
    (folder/'comparison.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive','native','baseline','output'):
        parser.add_argument(name,type=Path)
    args = parser.parse_args()
    compare(args.archive,args.native,args.baseline,args.output)


if __name__ == '__main__':
    main()
