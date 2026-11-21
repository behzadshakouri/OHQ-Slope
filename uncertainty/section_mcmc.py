"""Prepare native OHQ-MCMC input for one material's saturated conductivity."""
import argparse
import json
from pathlib import Path

from hydrology.section import keys, number, prepare, simulate_section


def export_mcmc(folder, scenario, calibration):
    prepare(scenario)
    keys(calibration, {'material', 'min_ksat_m_day', 'max_ksat_m_day', 'samples',
                       'burn_in', 'observations'}, 'Calibration')
    material = calibration['material']
    if not isinstance(material, str) or material not in scenario['materials']:
        raise ValueError('Choose a defined material for calibration.')
    low = number(calibration['min_ksat_m_day'], .001, 10., 'min_ksat_m_day')
    high = number(calibration['max_ksat_m_day'], low, 10., 'max_ksat_m_day')
    nominal = scenario['materials'][material]['ksat_m_day']
    if not low < nominal < high:
        raise ValueError('The conductivity bounds must bracket the starting value.')
    samples, burn_in = calibration['samples'], calibration['burn_in']
    if (type(samples) is not int or type(burn_in) is not int or not 20 <= samples <= 50000
            or samples % 2 or not 0 <= burn_in < samples-2):
        raise ValueError('Use an even 20–50000 samples and an earlier integer burn-in.')

    groups = calibration['observations']
    if not isinstance(groups, list) or not 1 <= len(groups) <= 32:
        raise ValueError('Provide 1–32 cell pressure observation series.')
    observations = []
    for group in groups:
        keys(group, {'column', 'layer', 'sigma_m', 'series'}, 'Observation')
        i, j = group['column'], group['layer']
        if (type(i) is not int or type(j) is not int or not 0 <= i < len(scenario['columns'])
                or not 0 <= j < len(scenario['columns'][i]['materials'])):
            raise ValueError('Observation column and layer must be valid zero-based cell indices.')
        sigma = number(group['sigma_m'], 1e-6, 100., 'Observation sigma_m')
        rows = group['series']
        if not isinstance(rows, list) or not 2 <= len(rows) <= 500:
            raise ValueError('Each observation series needs 2–500 time/head pairs.')
        previous = -1.
        csv = []
        for row in rows:
            keys(row, {'time_h', 'pressure_head_m'}, 'Observation row')
            time = number(row['time_h'], 0., scenario['duration_h'], 'Observation time')
            head = number(row['pressure_head_m'], -1e4, 1e4, 'Measured head')
            if time <= previous:
                raise ValueError('Observation times must increase.')
            previous = time
            csv.append(f'{time/24:.17g},{head:.17g}')
        observations.append((i, j, sigma, '\n'.join(csv)+'\n'))

    cells = {(i,j) for i,column in enumerate(scenario['columns'])
             for j,name in enumerate(column['materials']) if name == material}
    if not cells:
        raise ValueError('The selected material is unused.')

    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    forward = simulate_section(folder, scenario)
    lines = (folder/'section.ohq').read_text().splitlines()
    lines.append(f'create parameter;type=Parameter,name=zone_ksat,low={low},high={high},'
                 f'value={nominal},prior_distribution=log-normal')
    for i,j in sorted(cells):
        lines.append(f'setasparameter;object=Soil{i}_{j},parametername=zone_ksat,quantity=K_sat_original')
    for i,j in forward['hydrology']['outlet_cells']:
        if (i,j) in cells:
            lines.append(f'setasparameter;object=Seepage{i}_{j},parametername=zone_ksat,'
                         'quantity=K_sat_original')
    for k,(i,j,sigma,csv) in enumerate(observations):
        filename = f'calibration_pressure_{k}.csv'
        (folder/filename).write_text(csv)
        lines.append(f'create observation;type=Observation,name=FitPressure{k},object=Soil{i}_{j},'
                     f'expression=pressure_head,observed_data={filename},comparison_method=Least Squared,'
                     f'error_structure=normal,error_standard_deviation={sigma}')
    for key,value in dict(number_of_samples=samples, number_of_chains=2,
                          number_of_burnout_samples=burn_in, number_of_threads=1,
                          record_interval=1, number_of_post_estimate_realizations=0,
                          samples_filename='mcmc.txt').items():
        lines.append(f'setvalue;object=system,quantity={key},value={value}')
    result = folder/'calibration.ohq'
    result.write_text('\n'.join(lines)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path)
    parser.add_argument('calibration', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        model = export_mcmc(args.output_dir, json.loads(args.scenario.read_text()),
                            json.loads(args.calibration.read_text()))
    except (OSError, ValueError) as error:
        parser.exit(1, f'MCMC input export failed: {error}\n')
    print(f'Run OHQ-MCMC calibration.ohq . from {model.parent}')


if __name__ == '__main__':
    main()
