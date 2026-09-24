"""Combine the run files of cycles 1 to 3 into one table for the report.

Input : data/cycle1-runs.csv, data/cycle2-runs.csv, data/cycle3-runs.csv (raw data, one file per cycle)
Output: derived_data/cycles1-3.csv (column names as the report's dataset uses them)
Run   : python scripts/combine_cycles.py   (from the project folder)
"""
import csv, glob, os

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = []
for path in sorted(glob.glob(os.path.join(PROJ, 'data', 'cycle[1-3]-runs.csv'))):
    with open(path, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append([r['Run'], r['Cycle'], r['Additive A (wt%)'], r['Additive B (wt%)'], r['Score']])
os.makedirs(os.path.join(PROJ, 'derived_data'), exist_ok=True)
with open(os.path.join(PROJ, 'derived_data', 'cycles1-3.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['id', 'cycle', 'a', 'b', 'score'])
    w.writerows(rows)
print(len(rows), 'runs')
