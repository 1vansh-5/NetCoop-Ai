import json
from pathlib import Path
from netcoop import generate, SCENARIOS

if __name__=='__main__':
    folder=Path(__file__).resolve().parent/'samples'
    folder.mkdir(exist_ok=True)
    for scenario in SCENARIOS:
        (folder/f'{scenario}.json').write_text(json.dumps(generate(scenario),indent=2),encoding='utf-8')
    print(f'Wrote {len(SCENARIOS)} fresh scenarios to {folder}')
