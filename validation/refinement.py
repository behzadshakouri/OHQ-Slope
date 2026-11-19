"""Measure pressure sensitivity to column spatial resolution; no automatic convergence claim."""
import argparse
import json
from pathlib import Path
from hydrology.column import DEFAULT, simulate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('results/refinement.json'))
    args=parser.parse_args()
    folder=args.output.parent/(args.output.stem+'_files')
    cases={n:simulate(folder/str(n),{**DEFAULT,'cells':n},1) for n in (8,16,32)}
    differences=[]
    for a,b in ((8,16),(16,32)):
        pairs=list(zip(cases[a]['pressure_history'],cases[b]['pressure_history']))
        differences.append({'cells':[a,b],
            'maximum_transient_head_difference_m':max(abs(x['head_m']-y['head_m']) for x,y in pairs),
            'final_head_difference_m':abs(pairs[-1][0]['head_m']-pairs[-1][1]['head_m'])})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'specification':DEFAULT,'failure_depth_m':1,'differences':differences,
        'converged':False,'note':'Differences are diagnostics, not error bounds. A tolerance and independent benchmark are still required.',
        'engine_binary_sha256':cases[8]['engine_binary_sha256']},indent=2)+'\n')
    print(json.dumps(differences,indent=2))

if __name__=='__main__':main()
