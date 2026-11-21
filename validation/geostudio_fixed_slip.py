"""Compare native OHQ pressure transfer and fixed-surface FS with an archived snapshot."""
import argparse
from dataclasses import asdict, replace
import hashlib
from itertools import product
import json
import math
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from hydrology.column import interpolate
from stability.bishop import Slice, factor_of_safety
from stability.section import fixed_surface_history, screen_circular_surfaces
from validation.geostudio_archive import csv_rows


def digest(path):
    with path.open('rb') as stream:
        hasher = hashlib.sha256()
        for block in iter(lambda:stream.read(1024*1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def benchmark(archive_path, run_paths):
    source_sha = digest(archive_path)
    with ZipFile(archive_path) as archive:
        analysis = 'Slope Stability'
        snapshot, = [name for name in archive.namelist()
                     if name.startswith(analysis+'/') and name.endswith('.xml')]
        root = ElementTree.fromstring(archive.read(snapshot))
        definition, = [node for node in root.iter('Analysis') if node.findtext('Name') == analysis]
        method = definition.findtext('Method')
        time_h = float(definition.findtext('TimeIncrements/Start'))/3600
        folder = analysis+'/001'
        surfaces = csv_rows(archive,folder+'/slip_surface.csv')
        slip, = [row for row in surfaces if row['SlipNum'] == '44']
        rows = csv_rows(archive,folder+'/column_44.csv')
        # The audited homogeneous flume uses one effective friction angle.
        friction, = set(float(node.text) for node in root.iter('PhiPrime') if node.text)
        phi_b, = set(float(node.text) for node in root.iter('UnsatPhiB') if node.text)
    parts = [Slice(float(row['ColumnWidth']),float(row['ColumnWeight']),-float(row['BotAlphaX']),
                   float(row['CohesiveStrength']),math.radians(friction),
                   float(row['PoreWaterPressure']),math.radians(phi_b)) for row in rows]
    points = [(float(row['X']),float(row['Y'])) for row in rows]
    archived_pressure = [part.pressure_kpa for part in parts]
    suction_max_error = max(abs(max(0.,-part.pressure_kpa)*math.tan(part.suction_friction_rad)-
                                float(row['SuctionStrength']))
                            for part,row in zip(parts,rows,strict=True))
    if suction_max_error > 1e-6:
        raise ValueError('The archived suction terms do not follow the audited constant phi-b law.')
    saved_fs = float(slip['SlipFOS'])
    moment_replay = math.fsum(float(row['ResistingMomentX']) for row in rows)/math.fsum(
        float(row['ActivatingMomentX']) for row in rows)
    if abs(moment_replay/saved_fs-1) > .001:
        raise ValueError('The saved slice moment ledger does not reproduce the archived slip FOS.')
    runs = {}
    screening = {}
    candidates = list(product([.1,.25,.4],[1.65,1.8,1.95],[.1,.2,.3,.4]))
    for path in run_paths:
        data = json.loads(path.read_text())
        if data['inputs']['archive_sha256'] != source_sha or not data['balance_and_ledger_passed']:
            raise ValueError('Expected a verified OHQ pressure run from this same GeoStudio archive.')
        history = fixed_surface_history(data['native'],parts,points,data['inputs']['head_conversion_kn_m3'])
        pressure = [interpolate([(row['time_h'],row['pressure_kpa'][i]) for row in history],time_h)
                    for i in range(len(parts))]
        transferred = [replace(part,pressure_kpa=u) for part,u in zip(parts,pressure,strict=True)]
        errors = [a-b for a,b in zip(pressure,archived_pressure,strict=True)]
        runs[path.stem] = {'input_sha256':digest(path),'engine_binary_sha256':data['engine_binary_sha256'],
                           'model_sha256':data['native']['model_sha256'],
                           'columns':data['columns'],'max_layers':data['max_layers'],
                           'pressure_rmse_kpa':math.sqrt(math.fsum(e*e for e in errors)/len(errors)),
                           'pressure_bias_kpa':math.fsum(errors)/len(errors),
                           'pressure_at_snapshot_kpa':pressure,
                           'ohq_pressure_bishop_fs':factor_of_safety(transferred),'history':history}
        polygon = data['inputs']['archive_geometry']['polygon_m']
        ground = [tuple(point) for point in polygon[1:-1]]
        screening[path.stem] = {str(count):screen_circular_surfaces(
            data['native'],ground,candidates,count,12.,parts[0].cohesion_kpa,
            math.radians(friction),math.radians(phi_b)) for count in (30,60)}
    return {'archive_sha256':source_sha,'analysis':analysis,'slip_id':44,'time_h':time_h,
            'archived_method':method,'archived_fs':saved_fs,'archived_moment_ratio':moment_replay,
            'stability_method':'Simplified Bishop with constant phi-b suction strength',
            'archived_suction_strength_max_abs_error_kpa':suction_max_error,
            'archive_pressure_bishop_fs_without_suction':factor_of_safety(
                [replace(part,suction_friction_rad=0.) for part in parts]),
            'archive_pressure_bishop_fs':factor_of_safety(parts),
            'slice_base_points_m':points,'slices':[asdict(part) for part in parts],'runs':runs,
            'screening':{'unit_weight_kn_m3':12.,'geometry':'Continuous archived ground profile',
                         'candidate_parameters':['entry_x_m','exit_x_m','sagitta_m'],
                         'candidate_count':len(candidates),'runs':screening}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('runs',type=Path,nargs='+')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.resolve() in {p.resolve() for p in [args.archive,*args.runs]}:
        parser.error('Output must differ from each input file.')
    result = benchmark(args.archive,args.runs)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
