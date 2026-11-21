"""Plot the four probes from two native OHQ GeoStudio comparison exports."""
import argparse
import json
from pathlib import Path


def plot(coarse, fine, out):
    import matplotlib

    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    if coarse['inputs']['archive_sha256'] != fine['inputs']['archive_sha256']:
        raise ValueError('The two runs must use the same archive.')
    if coarse['probes'].keys() != fine['probes'].keys():
        raise ValueError('The runs must have the same pressure probes.')
    plt.rcParams.update({
        'font.size': 10, 'axes.spines.top': False,
        'axes.spines.right': False, 'pdf.fonttype': 42,
    })
    probes = list(fine['probes'].items())
    fig, axes = plt.subplots((len(probes) + 1)//2, 2, figsize=(10.3, 6.5),
                            layout='constrained', squeeze=False)
    fig.suptitle('Seepage pressure-head comparison', fontsize=17, fontweight='bold',
                 x=.02, ha='left')
    series_style = ((coarse, ':', '#a76324'), (fine, '-', '#08658e'))
    for index, ((key, probe), axis) in enumerate(zip(probes, axes.flat)):
        for pulse in fine['spec']['rainfall_schedule']:
            axis.axvspan(pulse['start_h'], pulse['end_h'], color='#eaf3f6', zorder=0)
        ref = probe['series']
        axis.plot([row['time_h'] for row in ref], [row['pressure_head_m'] for row in ref],
                  'k.--', lw=1.05, ms=3.7, label='Archived GeoStudio')
        for run, style, color in series_style:
            rows = run['probes'][key]['ohq_series']
            label = f'OHQ {run["columns"]} columns × {run["max_layers"]} layers'
            axis.plot([row['time_h'] for row in rows], [row['pressure_head_m'] for row in rows],
                      style, color=color, lw=1.8, label=label)
        axis.set(xlim=(ref[0]['time_h'], ref[-1]['time_h']), xlabel='Elapsed time (h)',
                 ylabel='Pressure head (m)')
        name = key.replace('_', ' ').capitalize()
        axis.set_title(f'{chr(65 + index)}   {name} · node {probe["node"]}',
                       loc='left', fontweight='bold')
        axis.grid(axis='y', alpha=.23)
    for axis in list(axes.flat)[len(probes):]:
        axis.set_visible(False)
    axes[0, 0].legend(loc='best', frameon=False, fontsize=8)
    fig.savefig(out/'Native_OHQ_Pressure_Comparison.pdf', facecolor='white')
    fig.savefig(out/'Native_OHQ_Pressure_Comparison.png', facecolor='white', dpi=300)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('coarse', type=Path)
    parser.add_argument('fine', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    coarse = json.loads(args.coarse.read_text())
    fine = json.loads(args.fine.read_text())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plot(coarse, fine, args.output_dir)


if __name__ == '__main__':
    main()
