"""Independent hydraulic/mechanical sampling with one OHQ solve per realization."""
import json
import math
from pathlib import Path
import random

from hydrology.column import simulate, validate_column
from stability.infinite_slope import factor_of_safety
from uncertainty.ensemble import finite, quantile

HYDRAULIC = ('ksat_m_day', 'alpha_per_m', 'n', 'initial_theta')


def validate_ranges(ranges, column, failure_depth):
    if not isinstance(ranges,dict) or not ranges or not set(ranges)<=set(HYDRAULIC):
        raise ValueError('Choose hydraulic uncertainty from Ksat, alpha, n, and initial_theta.')
    normalized={}
    for name in sorted(ranges):
        entry=ranges[name]
        if not isinstance(entry,dict) or set(entry)!={'min','max','distribution'}:
            raise ValueError(f'{name} needs min, max, and distribution.')
        low=finite(entry['min'],name);high=finite(entry['max'],name)
        if entry['distribution'] not in ('uniform','log_uniform'):
            raise ValueError('Hydraulic distributions are uniform or log_uniform.')
        if not low<=column[name]<=high:
            raise ValueError(f'{name} range must contain its nominal value.')
        if entry['distribution']=='log_uniform' and low<=0:
            raise ValueError('Log-uniform ranges must be strictly positive.')
        for endpoint in (low,high):validate_column({**column,name:endpoint},failure_depth)
        normalized[name]=dict(entry)
    return normalized


def sample(rng, entry):
    low,high=entry['min'],entry['max']
    if low==high:return low
    if entry.get('distribution','uniform')=='log_uniform':
        return math.exp(rng.uniform(math.log(low),math.log(high)))
    return rng.uniform(low,high)


def run_coupled(request,folder,progress,message,cancelled):
    count=request['samples'];rng=random.Random(request['seed'])
    fs_columns=None;pressure_columns=None;minima=[];crossings=[];records=[];reference=None;max_balance=0
    for index in range(count):
        if cancelled():raise InterruptedError('Run cancelled.')
        mechanical={name:sample(rng,request['parameters'][name]) for name in sorted(request['parameters'])}
        hydraulics={name:sample(rng,entry) for name,entry in request['hydraulic_uncertainty'].items()}
        spec={**request['column'],**hydraulics}
        trial=Path(folder)/'realizations'/f'{index:04d}';trial.mkdir(parents=True,exist_ok=True)
        record={'index':index,'mechanical':mechanical,'hydraulic':hydraulics}
        (trial/'parameters.json').write_text(json.dumps(record,indent=2)+'\n')
        message(f'Running OHQ realization {index+1} of {count}.')
        progress(index/count)
        (trial/'status.json').write_text(json.dumps({**record,'state':'running'},indent=2)+'\n')
        try:
            hydro=simulate(trial/'hydrology',spec,mechanical['failure_depth_m'],cancelled)
            history=hydro['pressure_history']
            if reference is None:
                reference=hydro
                fs_columns=[[] for _ in history];pressure_columns=[[] for _ in history]
            elif [row['time_h'] for row in history]!=[row['time_h'] for row in reference['pressure_history']]:
                raise ValueError('Realizations have different output times.')
            fs=[factor_of_safety(**mechanical,pressure_head_m=row['head_m']) for row in history]
            minimum=min(fs);crossing=next((row['time_h'] for row,value in zip(history,fs) if value<1),None)
            for i,(row,value) in enumerate(zip(history,fs)):
                fs_columns[i].append(value);pressure_columns[i].append(row['head_m'])
            minima.append(minimum);crossings.append(crossing)
            balance=hydro['water_balance_max_residual_m3'];max_balance=max(max_balance,balance)
            record.update(state='completed',minimum_fs=minimum,first_sampled_crossing_h=crossing,water_balance_max_residual_m3=balance)
            records.append(record)
            (trial/'status.json').write_text(json.dumps(record,indent=2)+'\n')
        except InterruptedError:
            (trial/'status.json').write_text(json.dumps({**record,'state':'cancelled'},indent=2)+'\n')
            raise
        except (ValueError,OSError) as error:
            record.update(state='failed',message=str(error))
            (trial/'status.json').write_text(json.dumps(record,indent=2)+'\n')
            # No partial-result probability: rejecting bad samples would bias it.
            raise ValueError(f'Realization {index+1} failed: {error}. No ensemble probability is reported; inspect its local status/log.') from error
        progress((index+1)/count)
    series=[]
    for row,values,heads in zip(reference['pressure_history'],fs_columns,pressure_columns):
        series.append({'time_h':row['time_h'],'pressure_head_m':quantile(heads,.5),
                       'pressure_p05_m':quantile(heads,.05),'pressure_p95_m':quantile(heads,.95),
                       'p05':quantile(values,.05),'median':quantile(values,.5),'p95':quantile(values,.95),
                       'probability_below_one':sum(value<1 for value in values)/count})
    probability=sum(value<1 for value in minima)/count
    hydro_summary={key:value for key,value in reference.items() if key not in ('pressure_history','profiles','specification')}
    hydro_summary.update(specification=request['column'],specification_role='Nominal inputs; each realization uses its sampled hydraulic overrides.',
                         realizations=count,water_balance_max_residual_m3=max_balance)
    return {'mode':'ensemble','samples':count,'seed':request['seed'], 'pressure_source':'ohq_column',
            'ohq_hydrology_used':True,'hydraulic_uncertainty_sampled':True,
            'distribution':'Independent uniform mechanical inputs and specified independent hydraulic distributions.',
            'series':series,'minimum_fs':{name:quantile(minima,q) for name,q in [('p05',.05),('median',.5),('p95',.95)]},
            'event_probability':probability,'monte_carlo_standard_error':math.sqrt(probability*(1-probability)/count),
            'minimum_fs_samples':minima,'first_sampled_crossing_h':crossings,'realizations':records,
            'hydraulic_uncertainty':request['hydraulic_uncertainty'],'hydrology':hydro_summary,
            'assumptions':['One OHQ solve per realization with independently sampled hydraulic and mechanical inputs.',
                'Geometry, failure depth, rainfall, and boundary conditions are fixed; no spatial random field or parameter correlations.',
                'Uniform infinite slope; fixed total unit weight per realization. No suction strength, ponded-water surcharge, seismic load, erosion, or deformation.',
                'FS minima and crossings are evaluated at selected output times; transient grid convergence remains a separate requirement.',
                'Pressure plot shows pointwise median and 5–95% range, not a single physical trajectory.',
                'All requested realizations must succeed; failed numerical/domain samples are not silently dropped.',
                'Zero observed failures do not establish zero probability. Example distributions are illustrative, not calibrated site information.']}
