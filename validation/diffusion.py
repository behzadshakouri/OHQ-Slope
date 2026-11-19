"""Small-amplitude unsaturated diffusion check, independent analytical reference.

A horizontal, homogeneous, closed column eliminates gravity. Linearizing
C(psi) psi_t = (K(psi) psi_x)_x about psi0 gives psi_t = D psi_xx.
A cosine mode has exact decay exp(-D*pi^2*t/L^2). Finite amplitude introduces
O(amplitude^2) pressure error, so this is not a nonlinear infiltration benchmark.
"""
import math
from pathlib import Path
from hydrology.column import ENGINE, run_engine


def constitutive(psi, alpha=1.5, n=1.6, theta_res=.05, theta_sat=.4, ksat=.5, connectivity=.5):
    m=1-1/n
    u=alpha*abs(psi)
    se=(1+u**n)**(-m)
    theta=theta_res+(theta_sat-theta_res)*se
    capacity=(theta_sat-theta_res)*m*n*alpha*u**(n-1)*(1+u**n)**(-m-1)
    conductivity=ksat*se**connectivity*(1-(1-se**(1/m))**m)**2
    return theta,capacity,conductivity


def benchmark(folder, cells=16, step_days=.0002):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    length=1.;base=-1.;amplitude=.001;duration=.2
    _,capacity,conductivity=constitutive(base)
    diffusivity=conductivity/capacity
    dz=length/cells
    positions=[(i+.5)*dz for i in range(cells)]
    initial=[base+amplitude*math.cos(math.pi*x/length) for x in positions]
    lines=[f'loadtemplate;filename={ENGINE}/resources/main_components.json',
           f'addtemplate;filename={ENGINE}/resources/unsaturated_soil.json']
    for i,psi in enumerate(initial):
        theta,_,_=constitutive(psi)
        # All representative elevations are zero: horizontal diffusion only.
        lines.append(f'create block;type=Soil,name=Cell{i},area=1,depth={dz},bottom_elevation={-dz},theta={theta:.17g},theta_res=0.05,theta_sat=0.4,alpha=1.5,n=1.6,L=0.5,K_sat_original=0.5,K_sat_scale_factor=1,specific_storage=0.01,aniso_ratio=1')
        lines.append(f'create observation;type=Observation,name=pressure_{i},object=Cell{i},expression=pressure_head,observed_data=,error_structure=normal,error_standard_deviation=1')
        if i:lines.append(f'create link;type=soil_to_soil_link,from=Cell{i-1},to=Cell{i},name=Diffusion{i}')
    settings={'simulation_start_time':0,'simulation_end_time':duration,'initial_time_step':step_days,
              'max_timestep_increase_factor':1,'minimum_timestep':1e-10,'nr_tolerance':1e-10,
              'maximum_time_allowed':120,'make_timeseries_uniform':'No','record_results':'No',
              'alloutputfile':'','observed_outputfile':'observations.csv','write_solution_details':'No','n_threads':1}
    lines.extend(f'setvalue;object=system,quantity={k},value={v}' for k,v in settings.items())
    model=folder/'diffusion.ohq';model.write_text('\n'.join(lines)+'\n')
    observations=run_engine(folder,model)
    simulated=[observations[f'pressure_{i}'][-1][1] for i in range(cells)]
    exact=[base+amplitude*math.cos(math.pi*x/length)*math.exp(-diffusivity*math.pi**2*duration/length**2) for x in positions]
    error=max(abs(a-b) for a,b in zip(simulated,exact))
    return {'cells':cells,'step_days':step_days,'duration_days':duration,'diffusivity_m2_day':diffusivity,
            'amplitude_m':amplitude,'maximum_head_error_m':error,
            'relative_to_initial_amplitude':error/amplitude,
            'scope':'Small-amplitude unsaturated diffusion; not full nonlinear rainfall infiltration.'}


def main():
    import argparse
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('results/diffusion-check.json'))
    args=parser.parse_args()
    folder=args.output.parent/(args.output.stem+'_files')
    results=[benchmark(folder/str(n),n) for n in (8,16,32)]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'checks':results,'reference':'Linearized Richards cosine-decay solution derived in docs/verification.md.'},indent=2)+'\n')
    for result in results:print(f"{result['cells']} cells: maximum head error {result['maximum_head_error_m']:.6g} m")

if __name__=='__main__':main()
