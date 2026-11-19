"""Independent ponding/saturation diagnostic; never a field-validation claim.

Conservative backward-Euler finite volumes with a surface reservoir and a
complementarity boundary: h>=0, infiltration is limited by available surface
water. The soil storage law includes the pinned OHQ compressibility branch,
implemented independently; surface gating and top-reference offsets are NOT
copied into the reference boundary. Differences therefore diagnose the
production discretization/boundary, not just its time integrator.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from hydrology.column import DEFAULT, ROOT, interpolate, simulate

SPEC = {**DEFAULT, 'depth_m': .5, 'duration_h': 6., 'rain_duration_h': 3.,
        'output_interval_h': .25, 'solver_step_h': 1/60}
FAILURE_DEPTH = .25


def retention(pressure, spec):
    """Return theta, dtheta/dpsi, K for the documented storage law."""
    n=spec['n'];m=1-1/n;alpha=spec['alpha_per_m']
    span=spec['theta_sat']-spec['theta_res']
    transition=-(.999**(-1/m)-1)**(1/n)/alpha
    if pressure >= transition:
        capacity=span*spec['specific_storage_per_m']/spec['theta_sat']
        theta=spec['theta_res']+span*.999+capacity*(pressure-transition)
        se=.999
    else:
        u=-alpha*pressure
        se=(1+u**n)**(-m)
        if se <= .001:raise ValueError('Reference reached dry retention clipping.')
        theta=spec['theta_res']+span*se
        capacity=span*m*n*alpha*u**(n-1)*(1+u**n)**(-m-1)
    k=spec['ksat_m_day']*se**spec['pore_connectivity']*(1-(1-se**(1/m))**m)**2
    return theta,capacity,k


def initial_pressure(spec):
    se=(spec['initial_theta']-spec['theta_res'])/(spec['theta_sat']-spec['theta_res'])
    m=1-1/spec['n']
    return -(se**(-1/m)-1)**(1/spec['n'])/spec['alpha_per_m']


def tridiagonal(lower, diagonal, upper, rhs):
    d=list(diagonal);r=list(rhs)
    for i in range(1,len(d)):
        multiplier=lower[i]/d[i-1]
        d[i]-=multiplier*upper[i-1];r[i]-=multiplier*r[i-1]
    result=[0.]*len(d);result[-1]=r[-1]/d[-1]
    for i in range(len(d)-2,-1,-1):result[i]=(r[i]-upper[i]*result[i+1])/d[i]
    return result


def reference(cells=64, step_days=.0005, spec=None, *, head_reference='centre',
              conductivity='arithmetic', surface_boundary='complementarity'):
    """Independent finite-volume integration; keyword variants are diagnostic.

    Defaults retain the cell-centred physical comparison. The top/maximum/
    smoothed combination reproduces production discrete laws for controlled
    attribution and implementation checks, not independent physical validation.
    """
    s=dict(SPEC if spec is None else spec)
    if not isinstance(cells,int) or isinstance(cells,bool) or cells<2 or not math.isfinite(step_days) or step_days<=0:
        raise ValueError('Use at least two cells and a finite positive step.')
    if head_reference not in ('centre','top') or conductivity not in ('arithmetic','maximum') or surface_boundary not in ('complementarity','smoothed'):
        raise ValueError('Unsupported controlled ponding variant.')
    dx=s['depth_m']/cells;half=dx/2
    offset=half if head_reference=='centre' else 0.
    state=[0.]+[initial_pressure(s)]*cells
    times=[i*s['output_interval_h'] for i in range(round(s['duration_h']/s['output_interval_h'])+1)]
    rain_end=s['rain_duration_h']/24
    t=0.;steps=0;max_residual=0.;history=[];profiles=[]
    max_balance=0.;initial=s['depth_m']*s['initial_theta']

    def top_flux(h,pressure,available):
        capacity=s['ksat_m_day']*(h-pressure+offset)/half
        if surface_boundary=='smoothed':return capacity*max(0.,h)/(max(0.,h)+.001)
        return min(available,capacity)

    def interface_k(left,right):
        return max(left,right) if conductivity=='maximum' else .5*(left+right)

    def fluxes(v,available):
        k=[retention(p,s)[2] for p in v[1:]]
        # The default is a standard ponded-head/water-availability boundary.
        flux=[top_flux(v[0],v[1],available)]
        flux.extend(interface_k(a,b)*(1-(right-left)/dx) for a,b,left,right in zip(k,k[1:],v[1:],v[2:]))
        flux.append(0.)
        return flux

    def advance(previous,dt,rain):
        old=[previous[0]]+[dx*retention(p,s)[0] for p in previous[1:]]
        available=rain+previous[0]/dt

        def residual(v):
            q=fluxes(v,available)
            return [v[0]-old[0]-dt*(rain-q[0])]+[dx*retention(p,s)[0]-a-dt*(qin-qout) for p,a,qin,qout in zip(v[1:],old[1:],q,q[1:])]

        v=list(previous)
        for iteration in range(30):
            r=residual(v);norm=max(abs(a) for a in r)
            if norm<1e-11:return v,norm
            size=len(v);lower=[0.]*size;diagonal=[0.]*size;upper=[0.]*size
            # Local dependence gives a tridiagonal Jacobian. Differentiate
            # each interface flux rather than copying engine expressions.
            q=fluxes(v,available)
            local_k=[retention(p,s)[2] for p in v[1:]]
            for j in range(size):
                eps=1e-7*max(1,abs(v[j]))
                changed_k=retention(v[j]+eps,s)[2] if j else None
                def changed_value(index):return v[index]+(eps if index==j else 0.)
                def changed_flux(face):
                    if face==cells:return 0.
                    if face==0:return top_flux(changed_value(0),changed_value(1),available)
                    left_k=changed_k if face==j else local_k[face-1]
                    right_k=changed_k if face+1==j else local_k[face]
                    return interface_k(left_k,right_k)*(1-(changed_value(face+1)-changed_value(face))/dx)
                changed={face:(changed_flux(face)-q[face])/eps for face in {max(0,j-1),j}}
                for i in range(max(0,j-1),min(size,j+2)):
                    if i==0:derivative=(1. if j==0 else 0.)+dt*changed.get(0,0.)
                    else:
                        derivative=(dx*retention(v[i],s)[1] if i==j else 0.)-dt*(changed.get(i-1,0.)-changed.get(i,0.))
                    if i==j:diagonal[i]=derivative
                    elif i==j+1:lower[i]=derivative
                    else:upper[i]=derivative
            correction=tridiagonal(lower,diagonal,upper,[-a for a in r])
            scale=1.
            for _ in range(25):
                trial=[a+scale*b for a,b in zip(v,correction)]
                if trial[0]>=-1e-12:
                    trial[0]=max(0.,trial[0])
                    if max(abs(a) for a in residual(trial))<norm:
                        v=trial;break
                scale*=.5
            else:raise ValueError('Ponding reference Newton line search failed.')
        raise ValueError('Ponding reference Newton iteration did not converge.')

    def record(hours):
        depths=[i*dx+offset for i in range(cells)]
        pressure=interpolate(list(zip(depths,state[1:])),FAILURE_DEPTH)
        history.append({'time_h':hours,'head_m':pressure,'surface_depth_m':state[0]})
        profiles.append({'time_h':hours,'pressure_head_m':state[1:],
                         'theta':[retention(p,s)[0] for p in state[1:]]})

    record(0.)
    for hours in times[1:]:
        target=hours/24
        while t<target-1e-13:
            dt=min(step_days,target-t)
            if t<rain_end-1e-13:dt=min(dt,rain_end-t)
            rain=s['rainfall_mm_h']*24/1000 if t<rain_end-1e-13 else 0.
            # Retry with a smaller step if the nonlinear solve fails; no
            # physical state clipping, redrawing, or silently skipped steps.
            for _ in range(14):
                try:new,residual=advance(state,dt,rain);break
                except ValueError:dt/=2
            else:raise ValueError('Ponding reference failed after step reductions.')
            state=new;t+=dt;steps+=1;max_residual=max(max_residual,residual)
            water=state[0]+dx*math.fsum(retention(p,s)[0] for p in state[1:])
            expected=initial+s['rainfall_mm_h']/1000*min(t*24,s['rain_duration_h'])
            max_balance=max(max_balance,abs(water-expected))
        record(hours)
    return {'cells':cells,'step_days':step_days,'steps':steps,'pressure_history':history,
            'reference_depths_m':[i*dx+offset for i in range(cells)],'profiles':profiles,
            'variant':{'head_reference':head_reference,'conductivity':conductivity,'surface_boundary':surface_boundary},
            'maximum_nonlinear_residual_m':max_residual,'water_balance_max_residual_m3':max_balance}


def hydrostatic_surface_depth(spec=SPEC):
    """Exact late sealed-column balance, if the whole column is on the linear branch."""
    n=spec['n'];m=1-1/n;span=spec['theta_sat']-spec['theta_res']
    transition=-(.999**(-1/m)-1)**(1/n)/spec['alpha_per_m']
    capacity=span*spec['specific_storage_per_m']/spec['theta_sat']
    length=spec['depth_m']
    intercept=spec['theta_res']+span*.999-capacity*transition
    total=length*spec['initial_theta']+spec['rainfall_mm_h']/1000*spec['rain_duration_h']
    surface=(total-length*intercept-capacity*length*length/2)/(1+capacity*length)
    if surface<0:raise ValueError('Hydrostatic saturated branch is not applicable.')
    return surface


def differences(case, ref):
    if [p['time_h'] for p in case['pressure_history']] != [p['time_h'] for p in ref['pressure_history']]:
        raise ValueError('Ponding comparison requires identical output times.')
    heads=[abs(a['head_m']-b['head_m']) for a,b in zip(case['pressure_history'],ref['pressure_history'])]
    surfaces=[p.get('surface_depth_m') for p in case['pressure_history']]
    if any(p is None for p in surfaces):surfaces=[p['surface_storage_m3'] for p in case['profiles']]
    return {'maximum_failure_pressure_difference_m':max(heads),'final_failure_pressure_difference_m':heads[-1],
            'maximum_surface_depth_difference_m':max(abs(a-b['surface_depth_m']) for a,b in zip(surfaces,ref['pressure_history']))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('results/ponding-check.json'))
    args=parser.parse_args();folder=args.output.parent/(args.output.stem+'_files')
    coarse,fine=reference(64,.000125),reference(128,.000125)
    temporal=reference(128,.0000625)
    cases=[simulate(folder/str(n),{**SPEC,'cells':n},FAILURE_DEPTH) for n in (8,16,32)]
    checks=[{'cells':n,**differences(case,fine),'water_balance_max_residual_m3':case['water_balance_max_residual_m3'],
             'final_maximum_theta':max(case['profiles'][-1]['theta'])} for n,case in zip((8,16,32),cases)]
    result={'specification':SPEC,'failure_depth_m':FAILURE_DEPTH,
            'scope':'Independent physical ponding boundary with the OHQ storage law; production boundary and reference coordinates differ.',
            'reference':fine,'reference_grid_difference':differences(coarse,fine),
            'reference_time_difference':differences(fine,temporal),'checks':checks,
            'analytical_final_surface_depth_m':hydrostatic_surface_depth(),
            'engine_binary_sha256':cases[0]['engine_binary_sha256'],
            'benchmark_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'engine_dependency':json.loads((ROOT/'config/engine.json').read_text()),
            'production_column_validated':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('reference_grid_difference','reference_time_difference','checks')},indent=2))


if __name__=='__main__':main()
