"""Compose a verified column adapter with the shared mechanical calculation."""
from hydrology.column import simulate, validate_column
from uncertainty.ensemble import run, validate


def validate_request(request):
    if not isinstance(request,dict):raise ValueError('Scenario must be an object.')
    source=request.get('pressure_source','prescribed_history')
    if source not in ('prescribed_history','ohq_column'):
        raise ValueError('Choose prescribed_history or ohq_column pressure source.')
    if source=='prescribed_history':return {**validate(request),'pressure_source':source}
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
    mechanical.pop('pressure_history')
    return {**mechanical,'pressure_source':source,'column':column}


def execute(request,folder,progress=lambda value:None,message=lambda text:None,cancelled=lambda:False):
    request=validate_request(request)
    if request['pressure_source']=='prescribed_history':
        return run(request,progress,cancelled)
    message('Running OHQ rainfall column and checking water balance.')
    progress(.05)
    hydro=simulate(folder/'hydrology',request['column'],request['parameters']['failure_depth_m']['value'],cancelled)
    if cancelled():raise InterruptedError('Run cancelled.')
    progress(.6)
    message('OHQ finished; calculating factor of safety.')
    result=run({**request,'pressure_history':hydro['pressure_history']},lambda value:progress(.6+.4*value),cancelled)
    result['pressure_source']='ohq_column'
    result['ohq_hydrology_used']=True
    result['hydrology']={key:value for key,value in hydro.items() if key!='pressure_history'}
    result['assumptions'][1]='Pressures come from one OHQ vertical-column run; hydraulic inputs and failure depth are fixed across mechanical realizations.'
    result['assumptions'] += ['Column has 1 m² horizontal area, ponding, and a sealed or unit-gradient base; no runoff, evaporation, or lateral flow. Ponded-water surcharge is omitted from mechanical stresses.',
                              'Pressure is mapped from OHQ top-reference total heads; spatial convergence must be checked for each new case.',
                              'Initial observation values are reconstructed from known model inputs because the pinned engine exports zero placeholders at time zero.']
    return result
