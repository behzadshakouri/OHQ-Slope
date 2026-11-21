"""Screen nested grids around X01 using the two saved pressure fields."""
import argparse
from itertools import product
import json
import math
from pathlib import Path
from zipfile import ZipFile

from stability.section import circular_slices, evaluate_slice_pressures, fixed_surface_history
from validation.geostudio_fixed_slip import digest
from validation.geostudio_pressure_field import SavedPressureField


def refine(archive, native_path, comparison_path):
    prior = json.loads(comparison_path.read_text())
    native = json.loads(native_path.read_text())
    if digest(archive) != prior['archive_sha256'] or digest(native_path) != prior['native_sha256']:
        raise ValueError('Inputs differ from the matched search.')
    with ZipFile(archive) as source:
        field = SavedPressureField(source)
    ground = [tuple(p) for p in native['inputs']['archive_geometry']['polygon_m'][1:-1]]
    args = (prior['unit_weight_kn_m3'], prior['cohesion_kpa'], math.radians(prior['friction_deg']),
            math.radians(prior['suction_friction_deg']))
    run = native['native']
    stages = []
    anchor = tuple(prior['circle_ids']['X01'])
    candidates = {tuple(p) for p in prior['expanded_critical']['accepted']}
    for count, increments in [(60, (.025,.025,.025)), (120, (.0125,.0125,.0125))]:
        candidates |= {tuple(round(x+d*i,7) for x,d,i in zip(anchor,increments,offset,strict=True))
                       for offset in product(range(-2,3),repeat=3)}
        accepted, rejected = {}, []
        for candidate in sorted(candidates):
            try:
                slices, points = circular_slices(ground,*candidate,count,*args)
                ohq = fixed_surface_history(run,slices,points)
                archived = evaluate_slice_pressures(slices,[field.pressure_history(*pt) for pt in points])
                if len(archived) != len(ohq) or any(abs(a['time_h']-b['time_h']) > 1e-10 for a,b in zip(archived,ohq)):
                    raise ValueError('Pressure fields must have matching saved times.')
                accepted[candidate] = (archived,ohq)
            except ValueError as error:
                rejected.append({'candidate':candidate,'reason':str(error)})
        if not accepted:
            raise ValueError('No admissible circles.')
        envelope = []
        times = [f['time_h'] for f in next(iter(accepted.values()))[0]]
        for j,time in enumerate(times):
            row = {'time_h':time}
            for i,label in enumerate(('archived','ohq')):
                winner = min(accepted,key=lambda c:accepted[c][i][j]['factor_of_safety'])
                row[label] = {'candidate':winner,'fs':accepted[winner][i][j]['factor_of_safety']}
            envelope.append(row)
        stages.append({'slices':count,'anchor':anchor,'increments_m':increments,
                       'accepted':len(accepted),'rejected':rejected,'envelope':envelope})
        anchor = min(envelope,key=lambda f:f['ohq']['fs'])['ohq']['candidate']
        candidates = set(accepted)
    finalists = sorted({f[k]['candidate'] for stage in stages for f in stage['envelope']
                        for k in ('archived','ohq')} | {tuple(prior['circle_ids']['X01'])})
    checks = []
    for candidate,count in product(finalists,(120,240,480)):
        try:
            slices,points = circular_slices(ground,*candidate,count,*args)
            ohq = fixed_surface_history(run,slices,points)
            archived = evaluate_slice_pressures(slices,[field.pressure_history(*pt) for pt in points])
            checks.append({'candidate':candidate,'slices':count,
                           'archived':min(archived,key=lambda f:f['factor_of_safety'])['factor_of_safety'],
                           'ohq':min(ohq,key=lambda f:f['factor_of_safety'])['factor_of_safety']})
        except ValueError as error:
            checks.append({'candidate':candidate,'slices':count,'rejected':str(error)})
    return {'archive_sha256':prior['archive_sha256'],'native_sha256':prior['native_sha256'],
            'stages':stages,'refinement':checks}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive','native','comparison','output'):
        parser.add_argument(name,type=Path)
    args = parser.parse_args()
    if args.output.resolve() in {p.resolve() for p in (args.archive,args.native,args.comparison)}:
        parser.error('Choose a separate output file.')
    result = refine(args.archive,args.native,args.comparison)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
