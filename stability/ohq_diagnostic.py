"""Run a read-only OHQ JSON FS diagnostic and require Python-reference parity."""
import hashlib
import math
from pathlib import Path

from hydrology.column import BINARY, ENGINE, ROOT, run_engine
from stability.infinite_slope import factor_of_safety

TEMPLATE=ROOT/'components/infinite_slope.json'


def evaluate(folder,rows,cancelled=lambda:False):
    """Evaluate up to 500 validated constant states in one isolated OHQ model.

    The final native observation is used, avoiding time-zero placeholders.
    No state is fed back into the hydrologic simulation. Domain failures or
    parity failures reject the calculation, rather than returning clamped FS.
    """
    if not isinstance(rows,list) or not 1<=len(rows)<=500:
        raise ValueError('JSON stability evaluation requires 1 to 500 states.')
    expected=[factor_of_safety(**row) for row in rows]
    if cancelled():raise InterruptedError('Run cancelled.')
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    lines=[f'loadtemplate;filename={ENGINE}/resources/main_components.json',
           f'addtemplate;filename={TEMPLATE}']
    for i,row in enumerate(rows):
        lines.append(f'create block;type=Infinite Slope Diagnostic,name=State{i},'+','.join(f'{name}={value:.17g}' for name,value in row.items()))
        for quantity in ('factor_of_safety','contact_valid'):
            lines.append(f'create observation;type=Observation,name={quantity}_{i},object=State{i},expression={quantity},observed_data=,error_structure=normal,error_standard_deviation=1')
    settings={'simulation_start_time':0,'simulation_end_time':1e-6,'initial_time_step':1e-6,
              'max_timestep_increase_factor':1,'minimum_timestep':1e-10,'nr_tolerance':1e-10,
              'maximum_time_allowed':120,'make_timeseries_uniform':'No','record_results':'No',
              'alloutputfile':'','observed_outputfile':'observations.csv','write_solution_details':'No','n_threads':1}
    lines.extend(f'setvalue;object=system,quantity={name},value={value}' for name,value in settings.items())
    model=folder/'stability.ohq';model.write_text('\n'.join(lines)+'\n')
    observations=run_engine(folder,model,cancelled)
    values=[]
    for i,reference in enumerate(expected):
        fs=observations[f'factor_of_safety_{i}'];valid=observations[f'contact_valid_{i}']
        if abs(fs[-1][0]-24e-6)>1e-10 or valid[-1][1]!=1:
            raise ValueError('OHQ JSON stability diagnostic is incomplete or outside the contact domain.')
        value=fs[-1][1]
        if not math.isclose(value,reference,rel_tol=1e-10,abs_tol=1e-10):
            raise ValueError(f'OHQ JSON FS differs from Python reference for state {i}: {value:g} versus {reference:g}.')
        values.append(value)
    return {'factor_of_safety':values,'maximum_absolute_difference':max(abs(a-b) for a,b in zip(values,expected)),
            'template_sha256':hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
            'engine_binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),
            'python_reference_checked':True,'method':'OHQ JSON diagnostic with read-only mechanical inputs; no hydraulic feedback.'}
