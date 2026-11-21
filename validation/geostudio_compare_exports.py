"""Compare a populated GeoStudio FS template with the matched Bishop replay."""
import argparse
import csv
import json
import math
from pathlib import Path


def read(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def compare(replay, geostudio, count):
    def key(row):
        return row['circle_id'],round(float(row['time_h']),10)

    expected = {key(row):row for row in read(replay) if int(row['count']) == count}
    recorded = {}
    for row in read(geostudio):
        if int(row['count']) != count:
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

    def metrics(errors):
        return {'bias':math.fsum(errors)/len(errors),
                'rmse':math.sqrt(math.fsum(e*e for e in errors)/len(errors)),
                'max_absolute':max(map(abs,errors))}

    return {'slice_count':count,'comparisons':len(expected),
            'bishop_archive_minus_geostudio':metrics(method_errors),
            'bishop_ohq_minus_bishop_archive':metrics(pressure_errors),'winning_circles':winning}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bishop_fs',type=Path)
    parser.add_argument('geostudio_fs',type=Path)
    parser.add_argument('--count',type=int,default=60)
    args = parser.parse_args()
    print(json.dumps(compare(args.bishop_fs,args.geostudio_fs,args.count),indent=2,allow_nan=False))


if __name__ == '__main__':
    main()
