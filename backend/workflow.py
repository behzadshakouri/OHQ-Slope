"""Compose a verified column adapter with the shared mechanical calculation."""
from hydrology.column import simulate, validate_column
from uncertainty.ensemble import run, validate
from uncertainty.coupled import validate_ranges, run_coupled
from stability.ohq_diagnostic import evaluate


def with_stability_engine(request,rows):
    engine=request.get('stability_engine','python_reference')
    if engine not in ('python_reference','ohq_json'):
        raise ValueError('Choose python_reference or ohq_json stability engine.')
    if engine=='ohq_json' and (request['samples']>100 or request['samples']*rows>10000):
        raise ValueError('OHQ JSON stability is limited to 100 realizations and 10000 sample-time evaluations.')
    return {**request,'stability_engine':engine}


def validate_request(request):
    if not isinstance(request,dict):raise ValueError('Scenario must be an object.')
    source=request.get('pressure_source','prescribed_history')
    if source not in ('prescribed_history','ohq_column'):
        raise ValueError('Choose prescribed_history or ohq_column pressure source.')
    ranges=request.get('hydraulic_uncertainty')
    if ranges is not None and not isinstance(ranges,dict):raise ValueError('hydraulic_uncertainty must be an object.')
    if source=='prescribed_history':
        if ranges:raise ValueError('Hydraulic uncertainty requires OHQ column mode.')
        return with_stability_engine({**validate(request),'pressure_source':source},len(request['pressure_history']))
    # Reuse mechanical validation without pretending these placeholders are
    # hydrologic outputs. They are removed from the normalized stored request.
    mechanical=validate({**request,'pressure_history':[{'time_h':0,'head_m':0},{'time_h':1,'head_m':0}]})
    depth=mechanical['parameters']['failure_depth_m']
    if mechanical['mode']=='ensemble' and not depth['min']==depth['value']==depth['max']:
        raise ValueError('Column mode holds failure depth fixed. Set its min and max equal to its value.')
    column=validate_column(request.get('column'),depth['value'])
    rows=int(column['duration_h']/column['output_interval_h'])+2
    if rows*mechanical['samples']>1000000:
        raise ValueError('Reduce samples or output times to one million mechanical evaluations.')
    if ranges:
        if mechanical['mode']!='ensemble':raise ValueError('Hydraulic uncertainty requires ensemble mode.')
        if mechanical['samples']>100:raise ValueError('Hydraulic ensembles are limited to 100 OHQ runs per job.')
        mechanical['hydraulic_uncertainty']=validate_ranges(ranges,column,depth['value'])
    else:
        mechanical.pop('hydraulic_uncertainty',None)
    mechanical.pop('pressure_history')
    return with_stability_engine({**mechanical,'pressure_source':source,'column':column},rows)


def execute(request,folder,progress=lambda value:None,message=lambda text:None,cancelled=lambda:False):
    request=validate_request(request)
    evaluator=None;diagnostics=[]
    if request['stability_engine']=='ohq_json':
        def evaluator(mechanical,history,index):
            message(f'Evaluating OHQ JSON stability realization {index+1}.')
            check=evaluate(folder/'stability'/f'{index:04d}',
                           [{**mechanical,'pressure_head_m':row['head_m']} for row in history],cancelled)
            diagnostics.append({key:value for key,value in check.items() if key!='factor_of_safety'})
            return check['factor_of_safety']
    def finish(result):
        result['stability_engine']=request['stability_engine']
        if diagnostics:
            result['stability_diagnostic']={**diagnostics[0],
                'realizations_checked':len(diagnostics),
                'maximum_absolute_difference':max(row['maximum_absolute_difference'] for row in diagnostics)}
        return result
    if request['pressure_source']=='prescribed_history':
        return finish(run(request,progress,cancelled,evaluator))
    if request.get('hydraulic_uncertainty'):
        return finish(run_coupled(request,folder,progress,message,cancelled,evaluator))
    message('Running OHQ rainfall column and checking water balance.')
    progress(.05)
    hydro=simulate(folder/'hydrology',request['column'],request['parameters']['failure_depth_m']['value'],cancelled)
    if cancelled():raise InterruptedError('Run cancelled.')
    progress(.6)
    message('OHQ finished; calculating factor of safety.')
    result=run({**request,'pressure_history':hydro['pressure_history']},lambda value:progress(.6+.4*value),cancelled,evaluator)
    result['hydraulic_uncertainty_sampled']=False
    result['pressure_source']='ohq_column'
    result['ohq_hydrology_used']=True
    result['hydrology']={key:value for key,value in hydro.items() if key!='pressure_history'}
    result['assumptions'][1]='Pressures come from one OHQ vertical-column run; hydraulic inputs and failure depth are fixed across mechanical realizations.'
    result['assumptions'] += ['Column has 1 m² horizontal area, ponding, and a sealed or unit-gradient base; no runoff, evaporation, or lateral flow. Ponded-water surcharge is omitted from mechanical stresses.',
                              'Pressure is mapped from OHQ top-reference total heads; spatial convergence must be checked for each new case.',
                              'Initial observation values are reconstructed from known model inputs because the pinned engine exports zero placeholders at time zero.']
    return finish(result)
