"""Offline representation fit to tabulated hydraulic curves; not observation calibration.

SciPy/NumPy are optional dependencies used only by this diagnostic.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from hydrology.column import ROOT


def curves(path):
    with Path(path).open(newline='') as stream:
        rows=list(csv.DictReader(stream))
    result={name:[] for name in ('retention','conductivity')}
    for row in rows:
        name=row['function'];pressure=float(row['pressure_magnitude_kPa']);value=float(row['value'])
        if name not in result or row['value_unit']!={'retention':'m3/m3','conductivity':'m/s'}[name]:
            raise ValueError('Expected retention in m3/m3 and conductivity in m/s.')
        if not math.isfinite(pressure) or pressure<0 or not math.isfinite(value) or value<=0:
            raise ValueError('Curve magnitudes must be finite, nonnegative suction and positive values.')
        if name=='retention' and value>=1:raise ValueError('Water content must be below one.')
        result[name].append((pressure,value))
    for name,points in result.items():
        if len(points)<5 or any(b[0]<=a[0] or b[1]>a[1] for a,b in zip(points,points[1:])):
            raise ValueError('Each curve needs at least five increasing suction points with nonincreasing values.')
    return result


def predict(suction_kpa,p,gamma_w=9.807):
    """Invert pinned OHQ storage law above its dry floor; flag invalid dry requests.

    Below the floor, returned values are the limiting state, not an invertible
    pressure prediction. This permits residual evaluation while exposing the limit.
    """
    psi=-suction_kpa/gamma_w
    n=p['n'];m=1-1/n;span=p['theta_sat']-p['theta_res'];alpha=p['alpha_per_m']
    transition=-(.999**(-1/m)-1)**(1/n)/alpha
    if psi>=transition:
        se=.999
        theta=p['theta_res']+span*(se+p['specific_storage_per_m']/p['theta_sat']*(psi-transition))
    else:
        raw=(1+(alpha*abs(psi))**n)**(-m)
        se=max(.001,raw)
        theta=p['theta_res']+span*se
    k=p['ksat_m_day']/86400*se**p['pore_connectivity']*(1-(1-se**(1/m))**m)**2
    floor=-min((.001**(-1/m)-1)**(1/n)/alpha,10000)
    return theta,k,psi>=floor


def fit(data,theta_scale=.01,mode='joint',fixed_l=None,starts=12):
    import numpy as np
    import scipy
    from scipy.optimize import least_squares
    if mode not in ('joint','retention','conductivity') or theta_scale<=0 or starts<1:
        raise ValueError('Use a supported mode, positive theta scale and at least one start.')
    names=['theta_res','theta_sat','alpha_per_m','n','ksat_m_day','pore_connectivity']
    bounds=[(1e-6,min(v for _,v in data['retention'])*.999),
            (max(max(v for _,v in data['retention'])*.95,
                 min(v for _,v in data['retention'])*1.001),.999999),
            (.01,20),(1.05,5),(.001,10),(0,1)]
    fixed={'specific_storage_per_m':.01}
    if fixed_l is not None:fixed['pore_connectivity']=fixed_l
    if mode=='retention':fixed.update(ksat_m_day=.5,pore_connectivity=.5)
    if mode=='conductivity':fixed.update(theta_res=.01,theta_sat=.4)
    active=[(name,bound) for name,bound in zip(names,bounds) if name not in fixed]
    logarithmic={'alpha_per_m','ksat_m_day'}
    lower=np.array([math.log(v[0]) if k in logarithmic else v[0] for k,v in active])
    upper=np.array([math.log(v[1]) if k in logarithmic else v[1] for k,v in active])
    def unpack(x):return {**fixed,**{k:math.exp(v) if k in logarithmic else float(v) for (k,_),v in zip(active,x)}}
    def residual(x):
        p=unpack(x);r=[]
        for name,points in data.items():
            if mode!='joint' and mode!=name:continue
            for suction,value in points:
                theta,k,_=predict(suction,p)
                delta=(theta-value)/theta_scale if name=='retention' else math.log10(k/value)
                r.append(delta/math.sqrt(len(points)))
        return r
    rng=np.random.default_rng(20261120);runs=[]
    for i in range(starts):
        x=(lower+upper)/2 if i==0 else rng.uniform(lower,upper)
        solution=least_squares(residual,x,bounds=(lower,upper),max_nfev=3000,ftol=1e-11,xtol=1e-11,gtol=1e-11)
        runs.append((float(np.dot(solution.fun,solution.fun)),solution))
    score,best=min(runs,key=lambda pair:pair[0]);p=unpack(best.x)
    metrics={};predictions=[]
    for name,points in data.items():
        if mode!='joint' and mode!=name:continue
        errors=[]
        for suction,value in points:
            theta,k,valid=predict(suction,p);pred=theta if name=='retention' else k
            errors.append(pred-value if name=='retention' else math.log10(pred/value))
            predictions.append({'function':name,'suction_kpa':suction,'source_value':value,'predicted_value':pred,
                                'within_invertible_head_range':valid})
        metrics[name]={'rmse' if name=='retention' else 'log10_rmse':math.sqrt(sum(v*v for v in errors)/len(errors)),
                       'max_absolute_error' if name=='retention' else 'max_absolute_log10_error':max(map(abs,errors))}
    return {'mode':mode,'theta_scale':theta_scale,'parameters':p,'objective':score,
            'fitted_parameters':[k for k,_ in active], 'fixed_parameters':fixed,
            'parameter_bounds':{k:list(v) for k,v in active},
            'optimizer':{'method':'scipy.optimize.least_squares (trf)','seed':20261120,'starts':starts,
                         'max_nfev_per_start':3000,'numpy_version':np.__version__,'scipy_version':scipy.__version__},
            'optimizer_success':bool(best.success),'optimizer_message':best.message,'multistart_objectives':[v for v,_ in runs],
            'bounds_hit':[k for (k,_),v,lo,hi in zip(active,best.x,lower,upper) if min(v-lo,hi-v)<1e-5*(hi-lo)],
            'metrics':metrics,'predictions':predictions}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('curves',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.curves.resolve()==args.output.resolve():parser.error('Output must differ from input.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text('{"state":"running","field_validated":false}\n')
    try:
        data=curves(args.curves)
        runs=[fit(data,mode=mode) for mode in ('retention','conductivity')]
        runs.extend(fit(data,theta_scale=scale) for scale in (.005,.01,.02))
        runs.append(fit(data,fixed_l=.5))
        result={'state':'completed','field_validated':False,'scope':'Tabulated-function representation only; no observation calibration or uncertainty inference.',
                'input_sha256':hashlib.sha256(args.curves.read_bytes()).hexdigest(),
                'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'soil_template_sha256':hashlib.sha256((ROOT/'OpenHydroQual/resources/unsaturated_soil.json').read_bytes()).hexdigest(),
                'pressure_conversion_gamma_w_kn_m3':9.807,'fixed_specific_storage_per_m':.01,
                'objective':'Mean squared theta residual/theta_scale plus mean squared log10 conductivity residual; weights are diagnostic choices, not measurement variances.',
                'bounds_scope':'Existing app bounds on alpha, n, Ksat and connectivity; residual and saturated contents bounded by curve-informed physical intervals.',
                'runs':runs}
    except (ValueError,OSError,KeyError,ImportError) as error:
        result={'state':'failed','message':str(error),'field_validated':False}
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('Saved '+str(args.output))
    if result['state']=='failed':parser.exit(1,result['message']+'\n')


if __name__=='__main__':main()
