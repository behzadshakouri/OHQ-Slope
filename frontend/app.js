'use strict';
const $ = id => document.getElementById(id);
const definitions = [
  ['cohesion_kpa', 'Effective cohesion', 'kPa', 5, 3, 7, 0, 1000],
  ['friction_deg', 'Friction angle', 'degrees', 30, 27, 33, .01, 89],
  ['unit_weight_kn_m3', 'Total unit weight', 'kN/m³', 18, 17, 19, 1, 40],
  ['slope_deg', 'Slope angle', 'degrees', 30, 28, 32, .1, 89],
  ['failure_depth_m', 'Vertical failure depth', 'm', 2, 1.8, 2.2, .01, 100],
];
let currentJob = null, timer = null, exported = null, viewVersion = 0, engineAvailable = false;
const advanced = [
 ['depth_m','Column depth (m)',2,.1,10], ['cells','Soil cells',16,2,32],
 ['alpha_per_m','Retention α (1/m)',1.5,.01,20], ['n','Retention n',1.6,1.05,5],
 ['theta_res','Residual water content',.05,.001,.99], ['theta_sat','Saturated water content',.4,.001,.99],
 ['specific_storage_per_m','Specific storage (1/m)',.01,.0001,.1], ['pore_connectivity','Pore connectivity L',.5,0,1],
 ['output_interval_h','Output spacing (h)',.25,.05,6], ['solver_step_h','Maximum solver step (h)',1/60,1/600,.1],
];
const hydraulicDefinitions=[
 ['ksat_m_day','Ksat (m/day)',.35,.65,'log_uniform'],
 ['alpha_per_m','α (1/m)',1.2,1.8,'uniform'],
 ['n','Retention n',1.4,1.8,'uniform'],
 ['initial_theta','Initial water content',.28,.32,'uniform'],
];
function hydraulicInputs() {
  $('hydraulic-parameters').replaceChildren();
  for(const [key,label,min,max,distribution] of hydraulicDefinitions) {
    const row=document.createElement('tr'),name=document.createElement('td');name.textContent=label;row.append(name);
    for(const [field,value] of [['min',min],['max',max]]) {
      const td=document.createElement('td'),input=document.createElement('input');
      Object.assign(input,{id:`hydraulic-${key}-${field}`,type:'number',step:'any',value});
      input.setAttribute('aria-label',`${label} ${field}`);td.append(input);row.append(td);
    }
    const td=document.createElement('td'),select=document.createElement('select');select.id=`hydraulic-${key}-distribution`;select.setAttribute('aria-label',`${label} distribution`);
    for(const [value,text] of [['uniform','Uniform'],['log_uniform','Log-uniform']]) {const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);}
    select.value=distribution;td.append(select);row.append(td);$('hydraulic-parameters').append(row);
  }
}
function hydraulicChanged() {
  const eligible=$('pressure-source').value==='ohq_column'&&$('mode').value==='ensemble';
  const active=eligible&&$('sample-hydraulics').checked;
  $('hydraulic-options').hidden=!eligible;$('sample-hydraulics').disabled=!eligible;$('hydraulic-ranges').hidden=!active;
  document.querySelectorAll('#hydraulic-ranges input,#hydraulic-ranges select').forEach(node=>{node.disabled=!active;});
  const limited=active||$('stability-engine').value==='ohq_json';
  $('samples').max=limited?'100':'10000';if(limited&&Number($('samples').value)>100)$('samples').value='10';
  if($('pressure-source').value==='ohq_column') $('driver-note').textContent=active?'Each realization samples hydraulic and mechanical properties and runs OHQ separately. Transient grid sensitivity remains.':'One OHQ run supplies pressure. Hydraulic inputs and failure depth are fixed; transient grid sensitivity remains.';
}
function parseRainfallSchedule(text) {
  if(!text.trim()) return [];
  return text.trim().split('\n').map((line,index)=>{
    const tokens=line.includes(',')?line.split(',').map(token=>token.trim()):line.trim().split(/\s+/);
    const parts=tokens.map(Number);
    if(tokens.some(token=>token==='')||parts.length!==3||!parts.every(Number.isFinite)) throw new Error(`Rain row ${index+1} needs start hour, end hour and intensity.`);
    return {start_h:parts[0],end_h:parts[1],intensity_mm_h:parts[2]};
  });
}
function rainfallChanged() {
  const hydro=$('pressure-source').value==='ohq_column';
  const scheduled=$('rain-mode').value==='schedule';
  $('rain-single').hidden=scheduled;$('rain-scheduled').hidden=!scheduled;
  $('rainfall').disabled=$('rain-duration').disabled=!hydro||scheduled;
  $('rain-schedule').disabled=!hydro||!scheduled;
}
function formulationChanged() {
  const centred=$('column-formulation').value==='cell_centred';
  $('column-cells').max=centred?'64':'32';
  if(!centred&&Number($('column-cells').value)>32)$('column-cells').value='32';
}
function advancedInputs() {
  $('column-advanced').replaceChildren();
  for(const [key,label,value,min,max] of advanced) {
    const wrapper=document.createElement('div'), text=document.createElement('label'), input=document.createElement('input');
    text.htmlFor=`column-${key}`;text.textContent=label;
    Object.assign(input,{id:`column-${key}`,type:'number',value,min,max,step:key==='cells'?'1':'any'});
    wrapper.append(text,input);$('column-advanced').append(wrapper);
  }
}
function driverChanged() {
  const hydro=$('pressure-source').value==='ohq_column';
  $('column-inputs').hidden=!hydro;$('prescribed-inputs').hidden=hydro;
  document.querySelectorAll('#column-inputs input,#column-inputs select,#column-inputs textarea').forEach(node=>{node.disabled=!hydro;});
  $('pressure').disabled=hydro;
  $('driver-title').textContent=hydro?'OHQ rainfall column':'Reference calculation';
  $('driver-note').textContent=hydro?'Prototype column: one OHQ run supplies pressure. Hydraulic inputs and failure depth are fixed; transient grid sensitivity remains.':'Pressure is supplied by you; no hydrologic simulation is used.';
  $('engine-status').textContent=engineAvailable?'OHQ console built and available.': 'OHQ is not built. Use Python reference with prescribed pressure, or build the console; see the README.';
  $('submit').disabled=(hydro||$('stability-engine').value==='ohq_json')&&!engineAvailable;
  rainfallChanged();modeChanged();
}

function inputs() {
  $('parameters').replaceChildren();
  for (const [key, label, unit, value, min, max, lower, upper] of definitions) {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = label;
    const small = document.createElement('small'); small.textContent = unit; name.append(small); row.append(name);
    for (const [type, initial] of [['value', value], ['min', min], ['max', max]]) {
      const cell = document.createElement('td');
      if (type !== 'value') cell.className = 'range-cell';
      const input = document.createElement('input');
      Object.assign(input, {type: 'number', id: `${key}-${type}`, value: initial, min: lower, max: upper, step: 'any', required: true});
      input.setAttribute('aria-label', `${label}, ${type}, ${unit}`);
      cell.append(input); row.append(cell);
    }
    $('parameters').append(row);
  }
}
function modeChanged() {
  const ensemble = $('mode').value === 'ensemble';
  $('scenario').classList.toggle('deterministic', !ensemble);
  $('ensemble-options').hidden = !ensemble;
  document.querySelectorAll('.range-cell input').forEach(input => {input.disabled = !ensemble;});
  const hydro=$('pressure-source').value==='ohq_column';
  for(const field of ['min','max']) $('failure_depth_m-'+field).disabled=hydro||!ensemble;
  $('range-help').textContent = ensemble ? 'Each mechanical range is sampled independently and uniformly. These example ranges are illustrative.' : 'The deterministic run uses the value column.';
  hydraulicChanged();
}
function reset() {
  inputs();advancedInputs();hydraulicInputs();$('sample-hydraulics').checked=false; $('mode').value = 'deterministic';$('pressure-source').value='ohq_column';$('stability-engine').value='python_reference';
  for(const field of ['value','min','max']) $('failure_depth_m-'+field).value='1';
  for(const [id,value] of Object.entries({rainfall:'40','rain-duration':'6',duration:'24',ksat:'0.5','initial-theta':'0.3',base:'sealed','column-formulation':'legacy_top'})) $(id).value=value;
  $('rain-mode').value='single';$('rain-schedule').value='0.5, 1, 40\n1.5, 2.5, 20';
  $('pressure').value = '0, 0\n2, 0.15\n4, 0.35\n6, 0.65\n8, 1\n10, 0.75\n12, 0.45';
  $('samples').value = '2000'; $('seed').value = '42';formulationChanged(); driverChanged(); $('form-error').textContent = '';
}
function scenario() {
  const parameters = {};
  for (const [key] of definitions) {
    parameters[key] = Object.fromEntries(['value', 'min', 'max'].map(field => [field, Number($(`${key}-${field}`).value)]));
    if ($('mode').value === 'deterministic') parameters[key].min = parameters[key].max = parameters[key].value;
  }
  const source=$('pressure-source').value;
  if(source==='ohq_column') {
    parameters.failure_depth_m.min=parameters.failure_depth_m.max=parameters.failure_depth_m.value;
    const column=Object.fromEntries(advanced.map(([key])=>[key,Number($('column-'+key).value)]));
    Object.assign(column,{rainfall_mm_h:Number($('rainfall').value),rain_duration_h:Number($('rain-duration').value),duration_h:Number($('duration').value),ksat_m_day:Number($('ksat').value),initial_theta:Number($('initial-theta').value),base:$('base').value,formulation:$('column-formulation').value});
    if($('rain-mode').value==='schedule') {
      column.rainfall_schedule=parseRainfallSchedule($('rain-schedule').value);
      column.rainfall_mm_h=column.rain_duration_h=0;
    }
    const request={mode:$('mode').value,pressure_source:source,stability_engine:$('stability-engine').value,parameters,column,samples:Number($('samples').value),seed:Number($('seed').value)};
    if($('mode').value==='ensemble'&&$('sample-hydraulics').checked) request.hydraulic_uncertainty=Object.fromEntries(hydraulicDefinitions.map(([key])=>[key,{min:Number($(`hydraulic-${key}-min`).value),max:Number($(`hydraulic-${key}-max`).value),distribution:$(`hydraulic-${key}-distribution`).value}]));
    return request;
  }
  const pressure_history = $('pressure').value.trim().split('\n').map((line, index) => {
    const parts = line.trim().split(/[,\s]+/).map(Number);
    if (parts.length !== 2 || !parts.every(Number.isFinite)) throw new Error(`Pressure row ${index+1} needs two numbers: time, head.`);
    return {time_h: parts[0], head_m: parts[1]};
  });
  return {mode: $('mode').value, pressure_source:source, stability_engine:$('stability-engine').value, parameters, pressure_history,
    samples: Number($('samples').value), seed: Number($('seed').value)};
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `Request failed (${response.status}).`);
  return value;
}
function element(tag, attrs, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function chart(rows) {
  const svg = $('chart'); svg.replaceChildren();
  const width=700, height=290, left=55, right=25, top=25, bottom=45;
  const start=rows[0].time_h, end=rows.at(-1).time_h;
  const maximum=Math.max(1.2, ...rows.map(row=>row.p95))*1.12;
  const x=t=>left+(t-start)/(end-start)*(width-left-right);
  const y=v=>height-bottom-v/maximum*(height-top-bottom);
  for(let i=0;i<=4;i++) {
    const value=maximum*i/4;
    svg.append(element('line',{x1:left,y1:y(value),x2:width-right,y2:y(value),stroke:'#e4eae7'}));
    svg.append(element('text',{x:left-10,y:y(value)+4,'text-anchor':'end'},value.toFixed(2)));
    const time=start+(end-start)*i/4;
    svg.append(element('text',{x:x(time),y:height-bottom+24,'text-anchor':'middle'},Number(time.toFixed(2))));
  }
  const path=(field)=>rows.map((row,i)=>`${i?'L':'M'}${x(row.time_h)},${y(row[field])}`).join(' ');
  const band=path('p95')+' '+[...rows].reverse().map(row=>`L${x(row.time_h)},${y(row.p05)}`).join(' ')+' Z';
  svg.append(element('path',{d:band,fill:'#d6e9e2'}));
  svg.append(element('line',{x1:left,y1:y(1),x2:width-right,y2:y(1),stroke:'#a4482c','stroke-dasharray':'6 5'}));
  svg.append(element('text',{x:width-right,y:y(1)-8,'text-anchor':'end',fill:'#a4482c'},'FS = 1'));
  svg.append(element('path',{d:path('median'),fill:'none',stroke:'#215c52','stroke-width':3}));
  svg.append(element('text',{x:width/2,y:height-5,'text-anchor':'middle'},'Time (hours)'));
  svg.append(element('text',{x:15,y:18},'FS'));
}
function pressureChart(rows) {
  const svg=$('pressure-chart');svg.replaceChildren();
  const left=55,right=675,top=20,bottom=185;
  const low=Math.min(0,...rows.map(row=>row.pressure_p05_m??row.pressure_head_m)), high=Math.max(0.1,...rows.map(row=>row.pressure_p95_m??row.pressure_head_m));
  const x=t=>left+(t-rows[0].time_h)/(rows.at(-1).time_h-rows[0].time_h)*(right-left);
  const y=v=>bottom-(v-low)/(high-low)*(bottom-top);
  for(let i=0;i<=4;i++) {const value=low+(high-low)*i/4;
    svg.append(element('line',{x1:left,y1:y(value),x2:right,y2:y(value),stroke:'#e4eae7'}));
    svg.append(element('text',{x:left-8,y:y(value)+4,'text-anchor':'end'},value.toFixed(2)));
    const time=rows[0].time_h+(rows.at(-1).time_h-rows[0].time_h)*i/4;
    svg.append(element('text',{x:x(time),y:bottom+23,'text-anchor':'middle'},Number(time.toFixed(2))));
  }
  if(rows[0].pressure_p05_m!==undefined) {
    const upper=rows.map((row,i)=>`${i?'L':'M'}${x(row.time_h)},${y(row.pressure_p95_m)}`).join(' ');
    const lower=[...rows].reverse().map(row=>`L${x(row.time_h)},${y(row.pressure_p05_m)}`).join(' ');
    svg.append(element('path',{d:upper+' '+lower+' Z',fill:'#dceaf4'}));
  }
  svg.append(element('path',{d:rows.map((row,i)=>`${i?'L':'M'}${x(row.time_h)},${y(row.pressure_head_m)}`).join(' '),fill:'none',stroke:'#376e96','stroke-width':3}));
  svg.append(element('text',{x:left,y:13},'Pressure head (m)'));
  svg.append(element('text',{x:350,y:225,'text-anchor':'middle'},'Time (hours)'));
}
function showResult(data) {
  $('empty').hidden = true; $('result').hidden = false;
  $('minimum').textContent = data.minimum_fs.median.toFixed(3);
  const ensemble=data.mode==='ensemble';
  $('probability-label').textContent = ensemble ? 'P(min FS < 1)' : 'Threshold crossed';
  $('probability').textContent = ensemble ? `${(100*data.event_probability).toFixed(1)}%` : data.event_probability ? 'Yes' : 'No';
  $('count').textContent = data.samples.toLocaleString();
  $('chart-note').textContent = data.hydraulic_uncertainty_sampled ? 'Solid lines: pointwise medians; shading: 5–95% ranges. Each realization has its own OHQ pressure history. Hydraulic and mechanical inputs are independent.' : ensemble ? 'Solid line: median FS. Shading: 5–95% range. Independent uniform mechanical uncertainty; pressure history held fixed.' : data.ohq_hydrology_used ? 'Fixed mechanical inputs with OHQ-simulated pressure. FS evaluated at the selected output times.' : 'Fixed mechanical inputs with prescribed pressure. FS evaluated at supplied times.';
  if(data.stability_engine==='ohq_json') $('chart-note').textContent+=' FS calculated by the OHQ JSON component and checked against Python.';
  chart(data.series);
  $('hydrology-result').hidden=!data.ohq_hydrology_used;
  if(data.ohq_hydrology_used) {
    $('water-balance').textContent=`Rainfall total: ${(data.hydrology.rainfall_total_m*1000).toFixed(1)} mm. Maximum water-balance residual: ${data.hydrology.water_balance_max_residual_m3.toExponential(2)} m³ over 1 m², across ${data.hydrology.realizations??1} OHQ run(s). Base: ${data.hydrology.specification.base==='sealed'?'sealed':'unit-gradient drainage'}. Formulation: ${data.hydrology.formulation==='cell_centred'?'cell-centred':'legacy top-reference'}.`;
    pressureChart(data.series);
  }
  $('series').replaceChildren();
  for (const row of data.series) {
    const tr=document.createElement('tr');
    for(const value of [row.time_h,row.pressure_head_m,row.p05,row.median,row.p95]) {
      const td=document.createElement('td'); td.textContent=value.toFixed(3);tr.append(td);
    }
    $('series').append(tr);
  }
  $('assumptions').replaceChildren();
  for(const text of data.assumptions) {const li=document.createElement('li');li.textContent=text;$('assumptions').append(li);}
}
async function history() {
  const data = await api('/api/jobs'); $('jobs').replaceChildren();
  if(!data.jobs.length) {const li=document.createElement('li');li.textContent='No runs yet.';$('jobs').append(li);}
  for(const job of data.jobs.slice(0,8)) {
    const li=document.createElement('li');const button=document.createElement('button');button.className='text-button';
    button.textContent=`${job.mode==='ensemble'?'Ensemble':'Deterministic'} · ${new Date(job.created_utc).toLocaleTimeString()}`;
    button.onclick=()=>openJob(job.id);const state=document.createElement('span');state.textContent=job.state;
    li.append(button,state);$('jobs').append(li);
  }
}
async function openJob(id) {
  clearTimeout(timer); const version=++viewVersion;currentJob=id;exported=null;$('download').disabled=true;
  $('result').hidden=true;$('empty').hidden=false;
  $('empty').firstElementChild.textContent='Waiting for results from this run.';
  await poll(id, version);
}
async function poll(id, version) {
  try {
    const job=await api(`/api/jobs/${id}`);
    if(version!==viewVersion)return;
    $('state').textContent=job.state;$('progress').value=job.progress;$('status').textContent=job.message;
    $('cancel').hidden=!['queued','running'].includes(job.state);
    if(job.state==='completed') {
      const [result,request,provenance]=await Promise.all(['result','request','provenance'].map(name=>api(`/api/jobs/${id}/${name}`)));
      if(version!==viewVersion)return;
      exported={job,request,result,provenance};showResult(result);$('download').disabled=false;
    }
    if(!['queued','running','completed'].includes(job.state)) $('empty').firstElementChild.textContent='This run did not produce results. See the run-status message.';
    await history();
    if(version===viewVersion && ['queued','running'].includes(job.state))timer=setTimeout(()=>poll(id,version),500);
  } catch(error) {if(version===viewVersion)$('status').textContent=`Unable to read run: ${error.message}`;}
}
$('scenario').addEventListener('submit',async event=>{
  event.preventDefault();$('form-error').textContent='';$('submit').disabled=true;
  try {const request=scenario();const job=await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});await openJob(job.id);}
  catch(error){$('form-error').textContent=error.message;}
  finally{$('submit').disabled=($('pressure-source').value==='ohq_column'||$('stability-engine').value==='ohq_json')&&!engineAvailable;}
});
$('cancel').onclick=async()=>{try{await api(`/api/jobs/${currentJob}`,{method:'DELETE'});}catch(error){$('status').textContent=error.message;}};
$('sample-hydraulics').onchange=hydraulicChanged;
$('column-formulation').onchange=formulationChanged;
$('rain-mode').onchange=rainfallChanged;
$('stability-engine').onchange=driverChanged;
$('mode').onchange=modeChanged;$('reset').onclick=reset;
$('pressure-source').onchange=()=>{if($('pressure-source').value==='ohq_column') {for(const field of ['value','min','max']) $('failure_depth_m-'+field).value=$('failure_depth_m-value').value;}driverChanged();};
$('download').onclick=()=>{if(!exported)return;const url=URL.createObjectURL(new Blob([JSON.stringify(exported,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=`slope-${exported.job.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
reset();api('/api/health').then(health=>{engineAvailable=health.ohq_hydrology_available;driverChanged();}).catch(error=>{$('engine-status').textContent=error.message;});history().catch(error=>{$('status').textContent=`Server unavailable: ${error.message}`;});
