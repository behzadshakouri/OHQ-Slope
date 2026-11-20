"""Piecewise-constant rainfall, in hours and mm/h over horizontal area."""
import math


def validate_schedule(schedule,duration):
    if not isinstance(schedule,list) or len(schedule)>100:
        raise ValueError('Rainfall schedule must be a list of at most 100 intervals.')
    result=[];previous_end=0.
    for index,row in enumerate(schedule):
        if not isinstance(row,dict) or set(row)!={'start_h','end_h','intensity_mm_h'}:
            raise ValueError('Each rain interval needs start_h, end_h and intensity_mm_h.')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in row.values()):
            raise ValueError('Rain interval values must be finite numbers.')
        start,end,rate=row['start_h'],row['end_h'],row['intensity_mm_h']
        if not 0<=start<end<=duration or start<previous_end or not 0<=rate<=200:
            raise ValueError(f'Rain interval {index+1} must be ordered, nonoverlapping, within duration and 0–200 mm/h.')
        if math.nextafter(start/24,end/24)>=end/24:
            raise ValueError('Rain interval is too narrow to represent in native time units.')
        previous_end=end;result.append(dict(row))
    return result


def intervals(spec):
    """Explicit wet/dry intervals covering the entire simulation, without ramps."""
    windows=spec.get('rainfall_schedule')
    if windows is None:
        windows=([{'start_h':0.,'end_h':spec['rain_duration_h'],'intensity_mm_h':spec['rainfall_mm_h']}]
                 if spec['rain_duration_h'] else [])
    result=[];end=0.
    for row in windows:
        if row['start_h']>end:result.append((end,row['start_h'],0.))
        result.append((row['start_h'],row['end_h'],row['intensity_mm_h']))
        end=row['end_h']
    if end<spec['duration_h']:result.append((end,spec['duration_h'],0.))
    return result


def cumulative_depth_m(spec,time_h):
    return math.fsum(rate*max(0.,min(time_h,end)-start)/1000 for start,end,rate in intervals(spec))
