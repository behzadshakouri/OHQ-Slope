'use strict';
const $ = id => document.getElementById(id);
const definitions = [
  ['cohesion_kpa', 'Effective cohesion', 'kPa', 5, 3, 7, 0, 1000],
  ['friction_deg', 'Friction angle', 'degrees', 30, 27, 33, .01, 89],
  ['unit_weight_kn_m3', 'Total unit weight', 'kN/m³', 18, 17, 19, 1, 40],
  ['slope_deg', 'Slope angle', 'degrees', 30, 28, 32, .1, 89],
  ['failure_depth_m', 'Vertical failure depth', 'm', 2, 1.8, 2.2, .01, 100],
];
let currentJob = null, timer = null, exported = null, viewVersion = 0, engineAvailable = false, stabilityEngineSelected = false;
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
const isSection = () => $('analysis').value === 'seepage_2d';
let sectionExample = null;
let sectionProbes = null;

function driverChanged() {
  const section = isSection();
  $('stability-inputs').hidden = $('stability-inputs').disabled = section;
  $('section-inputs').hidden = !section;
  if (!section) for (const [id] of sectionDimensions) $(id).disabled = true;
  if (!currentJob) {
    $('result-heading').textContent = section ? '2D seepage results' : 'Factor of safety';
    $('empty-prompt').textContent = section ? 'Run a scenario to see its pressure and water balance.' :
      'Run a scenario to see its stability response.';
    $('empty-help').hidden = section;
  }
  const hydro=$('pressure-source').value==='ohq_column';
  $('column-inputs').hidden=!hydro;$('prescribed-inputs').hidden=hydro;
  document.querySelectorAll('#column-inputs input,#column-inputs select,#column-inputs textarea').forEach(node=>{node.disabled=!hydro;});
  $('pressure').disabled=hydro;
  $('driver-title').textContent=section?'Native OHQ 2D seepage':hydro?'OHQ rainfall column':'Reference calculation';
  $('driver-note').textContent=section?'Run a configured soil section and inspect its pressure response and water balance.':hydro?'Prototype column: one OHQ run supplies pressure. Hydraulic inputs and failure depth are fixed; transient grid sensitivity remains.':'Pressure is supplied by you; no hydrologic simulation is used.';
  $('engine-status').textContent=engineAvailable?'OHQ console built and available.': 'OHQ is not built. Use Python reference with prescribed pressure, or build the console; see the README.';
  $('submit').disabled=(section||hydro||$('stability-engine').value==='ohq_json')&&!engineAvailable;
  rainfallChanged();
  if (!section) modeChanged();
  else updateSlopePreview();
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
  updateSlopePreview();
}
function defaultStabilityEngine() {
  return engineAvailable ? 'ohq_json' : 'python_reference';
}
function reset() {
  if (sectionExample) $('section-json').value = JSON.stringify(sectionExample, null, 2);
  stabilityEngineSelected = false;
  inputs();advancedInputs();hydraulicInputs();$('sample-hydraulics').checked=false; $('mode').value = 'deterministic';$('pressure-source').value='ohq_column';$('stability-engine').value=defaultStabilityEngine();
  for(const field of ['value','min','max']) $('failure_depth_m-'+field).value='1';
  for(const [id,value] of Object.entries({rainfall:'40','rain-duration':'6',duration:'24',ksat:'0.5','initial-theta':'0.3',base:'sealed','column-formulation':'legacy_top'})) $(id).value=value;
  $('rain-mode').value='single';$('rain-schedule').value='0.5, 1, 40\n1.5, 2.5, 20';
  $('pressure').value = '0, 0\n2, 0.15\n4, 0.35\n6, 0.65\n8, 1\n10, 0.75\n12, 0.45';
  $('samples').value = '2000'; $('seed').value = '42';formulationChanged(); driverChanged(); $('form-error').textContent = '';
}
function scenario() {
  if (isSection()) return {analysis: 'seepage_2d', section: JSON.parse($('section-json').value)};
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
const geometryNumber = new Intl.NumberFormat(undefined, {maximumFractionDigits:4});
const sectionDimensions = [['section-width','width_m'], ['section-height','cell_height_m']];
const materialColors = ['#c4ddd3','#e7cbac','#bccfe7','#d5c9e3','#e7dbac','#bbdbdf'];

function geometryFrame(width, height, lowerElevation = 0) {
  const scale = Math.min(548/width, 212/height);
  const left = (640-width*scale)/2;
  const bottom = (280+height*scale)/2;
  return {x:value=>left+scale*value,y:value=>bottom-scale*(value-lowerElevation)};
}

function drawSectionPreview(drawing, draft, stacks) {
  const {width_m:width, cell_height_m:dz, probes} = draft;
  const height = dz*Math.max(...stacks.map(stack=>stack.length));
  const dx = width/stacks.length;
  const names = [...new Set(stacks.flat())];
  const colors = new Map(names.map((name,index)=>[name,materialColors[index%materialColors.length]]));
  const {x,y} = geometryFrame(width,height);
  const surface = [];
  stacks.forEach((stack,i)=>{
    stack.forEach((material,j)=>{
      drawing.append(element('rect',{x:x(i*dx),y:y((stack.length-j)*dz),
        width:x(dx)-x(0),height:y(0)-y(dz),fill:colors.get(material),class:'slope-cell'}));
    });
    surface.push([x(i*dx),y(stack.length*dz)],[x((i+1)*dx),y(stack.length*dz)]);
  });
  drawing.append(element('polyline',{points:surface.join(' '),class:'slope-ground'}));
  let hasProbe = false;
  for (const [name,probe] of Object.entries(probes ?? {})) {
    if (!Number.isFinite(probe?.x_m) || !Number.isFinite(probe?.elevation_m) ||
        probe.x_m < 0 || probe.x_m > width || probe.elevation_m < 0) continue;
    const column = Math.min(stacks.length-1,Math.floor(probe.x_m/dx));
    if (probe.elevation_m > stacks[column].length*dz) continue;
    const marker = element('circle',{cx:x(probe.x_m),cy:y(probe.elevation_m),r:5,
      class:'slope-probe',tabindex:0,'aria-label':name});
    marker.append(element('title',{},name));
    drawing.append(marker);
    hasProbe = true;
  }
  const fmt = n=>geometryNumber.format(n);
  return {dimensions:[fmt(width)+' m wide',fmt(height)+' m high',stacks.length+' columns',fmt(dz)+' m cells'].join(' · '),
    legend:[...colors,...(hasProbe ? [['Pressure probe','#a4482c']] : [])],
    note:'Horizontal and vertical dimensions use the same scale.'};
}

function stabilityGeometryValue(key, sampled) {
  const values = (sampled ? ['min','max'] : ['value']).map(field=>{
    const input = $(key+'-'+field);
    return input.validity.valid ? input.valueAsNumber : NaN;
  });
  return values[0] <= values.at(-1) ? (values[0]+values.at(-1))/2 : NaN;
}

function drawStabilityPreview(drawing, angle, depth, columnDepth) {
  // A fixed five-metre segment of the idealized slope gives the preview a length reference.
  const radians = angle*Math.PI/180;
  const run = 5*Math.cos(radians);
  const rise = 5*Math.sin(radians);
  const lowerElevation = -Math.max(depth,columnDepth);
  const {x,y} = geometryFrame(run,rise-lowerElevation,lowerElevation);
  const a=[x(0),y(rise)], b=[x(run),y(0)], c=[x(0),y(rise-depth)], d=[x(run),y(-depth)];
  drawing.append(
    element('polygon',{points:[a,b,d,c].join(' '),fill:'#c4ddd3'}),
    element('polyline',{points:[a,b].join(' '),class:'slope-ground'}),
    element('polyline',{points:[c,d].join(' '),class:'slope-failure'}),
    element('line',{x1:a[0],y1:a[1],x2:c[0],y2:c[1],class:'slope-depth'})
  );
  const arcRadius = Math.min(46,Math.hypot(b[0]-a[0],b[1]-a[1])/2);
  if (arcRadius >= 14) {
    const start = [a[0]+arcRadius,a[1]];
    const end = [a[0]+arcRadius*Math.cos(radians),a[1]+arcRadius*Math.sin(radians)];
    drawing.append(
      element('line',{x1:a[0],y1:a[1],x2:start[0]+8,y2:a[1],class:'slope-reference'}),
      element('path',{d:'M '+start.join(' ')+' A '+arcRadius+' '+arcRadius+' 0 0 1 '+end.join(' '),
        class:'slope-reference'})
    );
  }
  for (const point of [a,c]) {
    drawing.append(element('line',{x1:point[0]-5,x2:point[0]+5,y1:point[1],y2:point[1],class:'slope-depth'}));
  }
  if (columnDepth > 0) {
    const base = y(-columnDepth);
    drawing.append(
      element('line',{x1:b[0],y1:b[1],x2:b[0],y2:base,class:'slope-column'}),
      element('line',{x1:b[0]-5,x2:b[0]+5,y1:base,y2:base,class:'slope-depth-cap'})
    );
  }
  const fmt = n=>geometryNumber.format(n);
  return {dimensions:[fmt(angle)+'° slope',fmt(depth)+' m vertical failure depth',
    ...(columnDepth ? [fmt(columnDepth)+' m column'] : [])].join(' · '),
    legend:[['Ground surface','#153d39'],['Failure plane','#a4482c'],
      ...(columnDepth ? [['OHQ column depth','#376888']] : [])],
    note:columnDepth > 0 && depth > columnDepth ?
      'Failure depth extends below the OHQ column.' :
      'Illustrative 5 m segment along the slope. Failure depth is measured vertically.'};
}

function updateSlopePreview(activeDimension) {
  const drawing = $('slope-drawing');
  drawing.replaceChildren();
  const section = isSection();
  const sampling = $('mode').value === 'ensemble';
  $('slope-mode').textContent = section ? '2D seepage grid' :
    sampling ? 'Ensemble midpoint' : 'Stability geometry';
  let preview;
  let message;
  if (section) {
    message = 'Enter valid dimensions and material stacks to preview the section.';
    let draft;
    try { draft = JSON.parse($('section-json').value); } catch {}
    for (const [id,key] of sectionDimensions) {
      $(id).disabled = !draft || typeof draft !== 'object' || Array.isArray(draft);
      if (activeDimension !== id) $(id).value = Number.isFinite(draft?.[key]) ? draft[key] : '';
    }
    const width = draft?.width_m, dz = draft?.cell_height_m, materials = draft?.materials;
    const stacks = Array.isArray(draft?.columns) ? draft.columns.map(column=>column?.materials) : [];
    if (Number.isFinite(width) && width >= .01 && width <= 1000 &&
        Number.isFinite(dz) && dz >= .001 && dz <= 100 && materials &&
        typeof materials === 'object' && !Array.isArray(materials) &&
        stacks.length >= 2 && stacks.length <= 32 &&
        stacks.every(stack=>Array.isArray(stack) && stack.length &&
          stack.every(name=>typeof name === 'string' && Object.hasOwn(materials,name))) &&
        stacks.reduce((sum,stack)=>sum+stack.length,0) <= 300) {
      preview = drawSectionPreview(drawing,draft,stacks);
    }
  } else {
    message = 'Enter a valid slope angle and failure depth to preview the section.';
    const hydro = $('pressure-source').value === 'ohq_column';
    const angle = stabilityGeometryValue('slope_deg',sampling);
    const depth = stabilityGeometryValue('failure_depth_m',sampling && !hydro);
    const column = $('column-depth_m');
    const columnDepth = hydro && column.validity.valid ? column.valueAsNumber || 0 : 0;
    if (Number.isFinite(angle) && Number.isFinite(depth)) {
      preview = drawStabilityPreview(drawing,angle,depth,columnDepth);
    }
  }
  $('slope').hidden = !preview;
  $('slope-description').textContent = preview ? 'Slope section. '+preview.dimensions : 'Slope preview unavailable';
  $('slope-dimensions').textContent = preview?.dimensions ?? '';
  $('slope-note').textContent = preview?.note ?? message;
  $('slope-legend').replaceChildren(...(preview?.legend ?? []).map(([label,color])=>{
    const item = document.createElement('li');
    const swatch = document.createElement('span');
    swatch.style.backgroundColor = color;
    item.append(swatch,label);
    return item;
  }));
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
function pressureChart(rows, chartId = 'pressure-chart') {
  const svg=$(chartId);svg.replaceChildren();
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
  const section = data.analysis === 'seepage_2d';
  $('result-heading').textContent = section ? '2D seepage results' : 'Factor of safety';
  $('section-result').hidden = !section;
  if (section) {
    $('empty').hidden = $('result').hidden = true;
    sectionProbes = data.probes;
    const hydro = data.hydrology;
    const volume = hydro.outlet_history.at(-1);
    $('section-budget').textContent =
      `Rainfall: ${data.rainfall_total_m3.toPrecision(4)} m³. Runoff: ${volume.cumulative_runoff_m3.toPrecision(4)} m³. Reviewed excess: ${volume.cumulative_surface_excess_m3.toPrecision(4)} m³. Seepage: ${volume.cumulative_discharge_m3.toPrecision(4)} m³. Maximum balance residual: ${hydro.water_balance_max_residual_m3.toExponential(2)} m³.`;
    const choices = $('section-probe');
    choices.replaceChildren();
    for (const name of Object.keys(sectionProbes)) {
      const option = document.createElement('option');
      option.value = option.textContent = name;
      choices.append(option);
    }
    pressureChart(sectionProbes[choices.value], 'section-chart');
    return;
  }
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
    button.textContent=`${job.mode==='seepage_2d'?'2D seepage':job.mode==='ensemble'?'Ensemble':'Deterministic'} · ${new Date(job.created_utc).toLocaleTimeString()}`;
    button.onclick=()=>openJob(job.id);const state=document.createElement('span');state.textContent=job.state;
    li.append(button,state);$('jobs').append(li);
  }
}
async function openJob(id) {
  clearTimeout(timer); const version=++viewVersion;currentJob=id;exported=null;$('download').disabled=true;
  $('section-result').hidden=true;$('result').hidden=true;$('empty').hidden=false;
  $('empty').firstElementChild.textContent='Waiting for results from this run.';
  await poll(id, version);
}
async function poll(id, version) {
  try {
    const job=await api(`/api/jobs/${id}`);
    if(version!==viewVersion)return;
    $('result-heading').textContent = job.mode === 'seepage_2d' ? '2D seepage results' : 'Factor of safety';
    $('empty-help').hidden = job.mode === 'seepage_2d';
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
  finally{$('submit').disabled=(isSection()||$('pressure-source').value==='ohq_column'||$('stability-engine').value==='ohq_json')&&!engineAvailable;}
});
$('cancel').onclick=async()=>{try{await api(`/api/jobs/${currentJob}`,{method:'DELETE'});}catch(error){$('status').textContent=error.message;}};
$('sample-hydraulics').onchange=hydraulicChanged;
$('column-formulation').onchange=formulationChanged;
$('rain-mode').onchange=rainfallChanged;
$('stability-engine').onchange=()=>{stabilityEngineSelected=true;driverChanged();};
$('mode').onchange=modeChanged;$('reset').onclick=reset;
$('analysis').onchange=driverChanged;
$('scenario').addEventListener('input', ({target}) => {
  if (/^(slope_deg-|failure_depth_m-|column-depth_m$|section-json$)/.test(target.id)) updateSlopePreview();
});
for (const [id, key] of sectionDimensions) {
  $(id).addEventListener('input', () => {
    const control = $(id);
    if (!control.validity.valid || !Number.isFinite(control.valueAsNumber)) {
      $('slope-note').textContent = 'Enter a valid dimension to update the section.';
      return;
    }
    const draft = JSON.parse($('section-json').value);
    draft[key] = control.valueAsNumber;
    $('section-json').value = JSON.stringify(draft, null, 2);
    updateSlopePreview(id);
  });
}
$('section-probe').onchange=()=>pressureChart(sectionProbes[$('section-probe').value], 'section-chart');
$('pressure-source').onchange=()=>{if($('pressure-source').value==='ohq_column') {for(const field of ['value','min','max']) $('failure_depth_m-'+field).value=$('failure_depth_m-value').value;}driverChanged();};
$('download').onclick=()=>{if(!exported)return;const url=URL.createObjectURL(new Blob([JSON.stringify(exported,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=`slope-${exported.job.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
reset();
api('/examples/seepage-2d.json').then(example=>{
  sectionExample = example;
  if (!$('section-json').value) $('section-json').value = JSON.stringify(example, null, 2);
  if (isSection()) updateSlopePreview();
}).catch(error=>{$('form-error').textContent=error.message;});
api('/api/health').then(health=>{
  engineAvailable=health.ohq_hydrology_available;
  if(!stabilityEngineSelected) $('stability-engine').value=defaultStabilityEngine();
  driverChanged();
}).catch(error=>{$('engine-status').textContent=error.message;});
history().catch(error=>{$('status').textContent=`Server unavailable: ${error.message}`;});
