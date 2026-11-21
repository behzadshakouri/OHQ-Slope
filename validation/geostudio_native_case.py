"""Run a first-pulse native OHQ comparison for the archived single-region flume."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from hydrology.column import BINARY, ROOT, initial_pressure, interpolate, validate_column
from validation.column_sensitivity import metrics
from validation.geostudio_archive import csv_rows, mesh_nodes
from validation.native_seepage_2d import grid_trial, sample_at_probe


def case_inputs(archive_path, manifest, boundary):
    hasher = hashlib.sha256()
    with archive_path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
    digest = hasher.hexdigest()
    if digest != boundary['archive_sha256'] or not any(
        row['sha256'] == digest for row in manifest['source_files']
    ):
        raise ValueError('Input archive hash differs from audited geometry or boundary evidence.')

    forcing = manifest['archived_forcing']
    material = manifest['candidate_constitutive_representation']
    duration = 2.
    schedule = [{'start_h': a, 'end_h': min(b, duration), 'intensity_mm_h': forcing['nominal_rainfall_mm_h']}
                for a, b in forcing['active_windows_h'] if a < duration]
    initial = forcing['initial_pressure_head_m']
    spec = dict(material['parameters'], initial_theta=material['theta_at_archived_initial_head'],
                cells=14, depth_m=1.4, duration_h=duration, output_interval_h=forcing['output_interval_h'],
                solver_step_h=1/60, rainfall_schedule=schedule, rainfall_mm_h=0, rain_duration_h=0,
                base='sealed', formulation='cell_centred', surface_boundary='reviewed_infiltration')
    if abs(initial_pressure(spec) - initial) > 1e-6:
        raise ValueError('Mapped water content does not reproduce the audited initial head.')
    probes = {'crest': 595, 'middle_face': 1691, 'lower_face': 2433, 'toe': 2838}
    analysis = 'Transient Seepage'
    with ZipFile(archive_path) as archive:
        snapshot = ElementTree.fromstring(archive.read(boundary['analysis_snapshot']))
        definitions = [item for item in snapshot.iter('Analysis')
                       if item.findtext('Name') == analysis and item.findtext('Kind') == 'SEEP/W']
        if len(definitions) != 1:
            raise ValueError('Expected one transient seepage definition in the archive snapshot.')
        analysis_id = definitions[0].findtext('ID')
        regions = [region for context in snapshot.iter('Context')
                   if context.findtext('AnalysisID') == analysis_id
                   for region in context.findall('GeometryUsesMaterials/GeometryUsesMaterial')]
        if len(regions) != 1:
            raise ValueError('This mapping expects exactly one archived material region.')
        nodes = mesh_nodes(archive.read(f'{analysis}/Mesh.ply'))
        initial_rows = csv_rows(archive, f'{analysis}/000/node.csv')
        if len(initial_rows) != len(nodes) or any(
            abs(float(row['PoreWaterPressure'])/9.807 - initial) > 1e-6 for row in initial_rows
        ):
            raise ValueError('Archive does not have the audited uniform initial pressure field.')
        refs = {name: {'node': node, 'position_m': nodes[node], 'series': []}
                for name, node in probes.items()}
        for step in csv_rows(archive, f'{analysis}/time.csv'):
            time_h = float(step['Time'])/3600
            if time_h > duration + 1e-9:
                break
            values = {int(row['Node']): float(row['PoreWaterPressure'])/9.807
                      for row in csv_rows(archive, f"{analysis}/{int(step['Step']):03d}/node.csv")}
            for entry in refs.values():
                entry['series'].append(dict(time_h=time_h, pressure_head_m=values[entry['node']]))
    if any(not entry['series'] for entry in refs.values()):
        raise ValueError('Missing saved reference time series.')

    geometry = manifest['archived_2d_geometry']
    # Explicitly verify the audited partition before reducing it to a staircase.
    if geometry['polygon_m'] != [[0,0],[0,1.4],[.5,1.4],[1.6,.3],[2,.3],[2,0]]:
        raise ValueError('Geometry differs from the audited crest, slope and toe section.')
    expected_boundaries = {
        'Lines-1': ('No Flux', 'Review=false'), 'Lines-2': ('RF', 'Review=true'),
        'Lines-3': ('RF (SLope)', 'Review=true'), 'Lines-4': ('RF', 'Review=true'),
        'Lines-5': ('No Flux', 'Review=false'), 'Lines-6': ('THR', 'Review=true'),
        'Lines-7': ('THR', 'Review=true'),
    }
    for line in boundary['boundary_assignments']:
        name, review = expected_boundaries.pop(line['line_id'])
        if line['boundary']['Name'] != name or review not in line['boundary']['Hydraulic']:
            raise ValueError('Seepage or rainfall assignment differs from the audited case.')
    if expected_boundaries:
        raise ValueError('Archive boundary evidence is incomplete.')
    return dict(archive_sha256=digest, archive_analysis=analysis, archive_geometry=geometry,
                material_region=regions[0].attrib, material_fit=material,
                boundary_assignments=boundary['boundary_assignments'],
                initial_pressure_head_m=initial, head_conversion_kn_m3=9.807, spec=spec, probes=refs,
                rainfall_mapping='Nominal 67.5 mm/h over horizontal plan area on crest, face and toe.',
                boundary_mapping='Sealed back and base. Reviewed rainfall capacity on terrace tops, '
                    'with separate one-way seepage on exposed risers and right toe. '
                    'Excess is collected separately without routing over the surface.',
                geometry_mapping='Nearest-height staircase sampled at each horizontal cell centre; unit flume width.')


def run_case(folder, inputs, columns, layers, step_s, budget_s):
    spec = dict(inputs['spec'], cells=layers, solver_step_h=step_s/3600)
    validate_column(spec, 0.1)
    width = 2.
    dx, dz = width/columns, spec['depth_m']/layers
    heights = [max(.3, min(1.4, 1.9 - (i+.5)*dx)) for i in range(columns)]
    counts = [math.floor(z/dz+.5+1e-10) for z in heights]
    run = grid_trial(folder, spec, [0]*columns, width_m=width, column_cells=counts,
                     exposed_step_outlets=True, right_outlet_rows=range(counts[-1]),
                     engine_seconds=budget_s)
    probes = {}
    for name, ref in inputs['probes'].items():
        simulated = sample_at_probe(run, *ref['position_m'])
        series = [(v['time_h'], v['pressure_head_m']) for v in simulated]
        matched = [dict(time_h=r['time_h'], pressure_head_m=interpolate(series, r['time_h']))
                   for r in ref['series']]
        probes[name] = {**ref, 'ohq_series': matched,
                        'metrics': metrics(matched, ref['series'], 'pressure_head_m')}
    outlet = run['outlet_history'][-1]
    rainfall = width * sum(r['intensity_mm_h']*(r['end_h']-r['start_h'])/1000
                           for r in spec['rainfall_schedule'])
    storage_change = math.fsum(rows[-1]['water_storage_m3'] - rows[0]['water_storage_m3']
                               for rows in run['histories'])
    mass_balance = dict(rainfall_m3=rainfall, soil_and_surface_storage_change_m3=storage_change,
                        reviewed_surface_excess_m3=outlet['cumulative_surface_excess_m3'],
                        seepage_discharge_m3=outlet['cumulative_discharge_m3'],
                        max_native_residual_m3=run['water_balance_max_residual_m3'])
    passed = (run['water_balance_max_residual_m3'] <= 1e-7 and
              run['minimum_native_excess_increment_m3'] >= -1e-9 and
              run['minimum_native_outlet_increment_m3'] >= -1e-9 and
              max(abs(row['surface_storage_m3']) for column in run['histories'] for row in column) <= 1e-9)
    return dict(state='completed', balance_and_ledger_passed=passed, inputs=inputs, spec=spec,
                columns=columns, max_layers=layers, probes=probes, mass_balance=mass_balance,
                archive_section_area_m2=inputs['archive_geometry']['area_m2'],
                staircase_section_area_m2=dx*dz*sum(counts), native=run,
                engine=json.loads((ROOT/'config/engine.json').read_text()),
                engine_binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('boundary_evidence', type=Path)
    parser.add_argument('--columns', type=int, choices=(8,16), default=8)
    parser.add_argument('--layers', type=int, choices=(14,28), default=14)
    parser.add_argument('--step-seconds', type=float, choices=(30.,60.), default=60.)
    parser.add_argument('--engine-seconds', type=int, default=600)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {p.resolve() for p in (args.archive,args.manifest,args.boundary_evidence)}:
        parser.error('The output path must differ from the input paths.')
    inputs = case_inputs(args.archive, json.loads(args.manifest.read_text()),
                         json.loads(args.boundary_evidence.read_text()))
    result = run_case(args.output.parent/(args.output.stem+'_files'), inputs, args.columns, args.layers,
                      args.step_seconds, args.engine_seconds)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(f"Saved {args.output}: {'balance passed' if result['balance_and_ledger_passed'] else 'balance failed'}")
    return 0 if result['balance_and_ledger_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
