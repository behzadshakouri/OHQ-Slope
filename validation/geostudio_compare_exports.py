"""Compare a populated GeoStudio FS template with the matched Bishop replay."""
import argparse
import csv
import json
import math
from pathlib import Path


def read(path):
    with path.open(newline='',encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def metrics(errors):
    return {'bias':math.fsum(errors)/len(errors),
            'rmse':math.sqrt(math.fsum(e*e for e in errors)/len(errors)),
            'max_absolute':max(map(abs,errors))}


def compare(replay, geostudio, count, circle=None):
    def key(row):
        return row['circle_id'],round(float(row['time_h']),10)

    expected = {key(row):row for row in read(replay) if int(row['count']) == count and (circle is None or row['circle_id'] == circle)}
    recorded = {}
    for row in read(geostudio):
        if int(row['count']) != count or (circle is not None and row['circle_id'] != circle):
            continue
        match = key(row)
        if match in recorded:
            raise ValueError(f'Duplicate GeoStudio result for {match}.')
        value = float(row['geostudio_fs'])
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f'Invalid GeoStudio FS for {match}.')
        recorded[match] = value
    if not expected or recorded.keys() != expected.keys():
        raise ValueError('GeoStudio export must contain one result per matched circle and saved time.')
    by_time = {}
    method_errors, pressure_errors = [], []
    for (circle,t),row in expected.items():
        archive = float(row['bishop_with_archived_pressure'])
        ohq = float(row['bishop_with_ohq_pressure'])
        native = recorded[circle,t]
        method_errors.append(archive-native)
        pressure_errors.append(ohq-archive)
        by_time.setdefault(t,[]).append((circle,native,archive,ohq))
    winning = [{'time_h':t,**{label:min(rows,key=lambda row:(row[i],row[0]))[0]
                             for i,label in enumerate(('geostudio','archived_pressure','ohq_pressure'),1)}}
               for t,rows in sorted(by_time.items())]

    return {'slice_count':count,'comparisons':len(expected),
            'bishop_archive_minus_geostudio':metrics(method_errors),
            'bishop_ohq_minus_bishop_archive':metrics(pressure_errors),'winning_circles':winning}


def compare_slices(geometry, pressures, geostudio, count, circle):
    """Compare normalized exports in common units; report GeoStudio minus reference."""
    geometry_fields = ('x_m','base_y_m','width_m','weight_kn_per_m','downslope_angle_deg')

    def index(path, timed):
        result = {}
        for row in read(path):
            if int(row['count']) != count or row['circle_id'] != circle:
                continue
            number = int(row['slice_no'])
            if not 1 <= number <= count:
                raise ValueError(f'Invalid slice number in {path.name}: {number}.')
            time = float(row['time_h']) if timed else None
            if timed and not math.isfinite(time):
                raise ValueError(f'Invalid time in {path.name}.')
            key = (round(time,10),number) if timed else number
            if key in result:
                raise ValueError(f'Duplicate slice record in {path.name}: {key}.')
            result[key] = row
        return result

    def number(row, field):
        try:
            value = float(row[field])
        except (ValueError,TypeError,KeyError) as error:
            raise ValueError(f'Missing or invalid slice field {field}.') from error
        if not math.isfinite(value) or (field in ('width_m','weight_kn_per_m') and value <= 0):
            raise ValueError(f'Invalid slice field {field}: {value}.')
        return value

    reference_geometry = index(geometry,False)
    if set(reference_geometry) != set(range(1,count+1)):
        raise ValueError('Reference geometry must have one row per slice.')
    reference_pressure = index(pressures,True)
    actual = index(geostudio,True)
    if not reference_pressure or actual.keys() != reference_pressure.keys():
        missing = sorted(reference_pressure.keys()-actual.keys())[:5]
        extra = sorted(actual.keys()-reference_pressure.keys())[:5]
        raise ValueError(f'Slice/time coverage differs. First missing: {missing}. First extra: {extra}.')
    errors = {name:[] for name in (*geometry_fields,'pressure_vs_archived_kpa','pressure_vs_ohq_kpa')}
    locations = sorted(actual)
    for key in locations:
        row = actual[key]
        baseline = reference_geometry[key[1]]
        for field in geometry_fields:
            errors[field].append(number(row,field)-number(baseline,field))
        for source in ('archived','ohq'):
            errors[f'pressure_vs_{source}_kpa'].append(
                number(row,'pressure_kpa')-number(reference_pressure[key],f'{source}_pressure_kpa'))
    fields = {}
    for field,values in errors.items():
        i = max(range(len(values)),key=lambda i:abs(values[i]))
        fields[field] = {**metrics(values),'worst_time_h':locations[i][0],
                         'worst_slice_no':locations[i][1]}
    return {'circle_id':circle,'slice_count':count,'comparisons':len(locations),'fields':fields}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bishop_fs',type=Path)
    parser.add_argument('geostudio_fs',type=Path)
    parser.add_argument('--count',type=int,default=60)
    parser.add_argument('--circle',help='Compare a single circle, for example C01.')
    parser.add_argument('--slice-export',type=Path)
    parser.add_argument('--slice-geometry',type=Path)
    parser.add_argument('--slice-pressures',type=Path)
    args = parser.parse_args()
    slice_inputs = (args.slice_export,args.slice_geometry,args.slice_pressures)
    if any(slice_inputs) and (not all(slice_inputs) or not args.circle):
        parser.error('Slice comparison requires all three slice files and --circle.')
    result = compare(args.bishop_fs,args.geostudio_fs,args.count,args.circle)
    if all(slice_inputs):
        result['slice_comparison'] = compare_slices(args.slice_geometry,args.slice_pressures,
                                                    args.slice_export,args.count,args.circle)
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__ == '__main__':
    main()
