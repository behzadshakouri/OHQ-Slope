"""Preview or apply the tracked GitHub About and topics; never push source."""
import argparse
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Update GitHub using GH_TOKEN or GITHUB_TOKEN; default is local preview only.')
    args=parser.parse_args()
    settings=json.loads((ROOT/'.github/repository.json').read_text())
    if settings['owner']!='behzadshakouri' or settings['name']!='OHQ-Slope':
        parser.error('This helper only targets behzadshakouri/OHQ-Slope.')
    topics=settings['topics']
    if not isinstance(topics,list) or len(topics)>20 or len(set(topics))!=len(topics) or any(not isinstance(t,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,49}',t) for t in topics):
        parser.error('Topics must be unique lowercase GitHub topic names (maximum 20).')
    print(json.dumps(settings,indent=2))
    if not args.apply:
        print('Preview only. No network request, GitHub update, or source push was made.')
        return
    token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if not token:parser.error('Configure GH_TOKEN or GITHUB_TOKEN for the owner account before using --apply. Do not put tokens in this repository.')
    def api(method,path,payload=None):
        request=Request('https://api.github.com'+path,method=method,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={'Accept':'application/vnd.github+json','Content-Type':'application/json',
                     'Authorization':'Bearer '+token,'X-GitHub-Api-Version':'2026-03-10',
                     'User-Agent':'OHQ-Slope-repository-settings'})
        with urlopen(request,timeout=30) as response:return json.load(response)
    try:
        account=api('GET','/user')['login']
        if account.lower()!=settings['owner'].lower():
            parser.error('Authenticated account is '+account+'; expected '+settings['owner']+'. No repository changes made.')
        path='/repos/'+settings['owner']+'/'+settings['name']
        api('PATCH',path,{key:settings[key] for key in ('description','homepage')})
        print('About description and website updated.')
        api('PUT',path+'/topics',{'names':topics})
        print('Topics updated. No source was pushed.')
    except HTTPError as error:
        parser.exit(1,f'GitHub returned HTTP {error.code}. If the About update succeeded, it remains applied; rerun after fixing repository Administration permission.\n')
    except URLError:
        parser.exit(1,'Could not reach GitHub. Any successful earlier update remains applied; the helper can be rerun.\n')


if __name__=='__main__':main()
