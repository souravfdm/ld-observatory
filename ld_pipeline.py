"""Loss & Damage Observatory: turn the two KoboToolbox xlsx exports into anonymised dashboard aggregates.

Only aggregated figures leave this script. Names, NID numbers, phone numbers, GPS points and
household-level records are never written to the public site.
"""
import json, math, itertools, datetime as dt
import numpy as np, pandas as pd
from scipy import stats

PARAMS = dict(win_start=2021, win_end=2026, years=5, max_crop_pct=100, max_crop_val=10_000_000, max_liv_per=300_000,
              max_pou_n=1000, max_pou_per=5000, min_low=100, fx=124, min_cell=5, drought_physical_exclude=True)

ASSETS = ['Residence', 'Agricultural land', 'Plants (privately owned)', 'Houses', 'Shop', 'Boats', 'Furniture', 'Utensils', 'Fuel',
          'Educational Materials', 'Fisheries', 'Other']
ALAB = ['Residence/homestead', 'Agricultural land', 'Trees (private)', 'Houses', 'Shop', 'Boats', 'Furniture', 'Utensils', 'Fuel',
        'Educational materials', 'Fisheries', 'Other']
PURP = ['Expenses (food, daily needs)', 'Cost of treatment', 'Agriculture/Livelihood', 'Repair/remodeling of the house', 'Migration/Migration',
        'Cost of Education/Study', 'Previous loan repayment', 'Other (specify)']
PLAB = ['Food / daily needs', 'Medical treatment', 'Agriculture / livelihood', 'House repair', 'Migration', 'Education', 'Repay old loan', 'Other']
TYPES = ['Flood', 'Storms/cyclones', 'River erosion', 'Drought', 'Lightning', 'Cold Wave', 'Other']
DISTRICTS = {'Northern': ['Kurigram', 'Gaibandha'], 'Southern': ['Khulna', 'Satkhira', 'Patuakhali', 'Bagerhat']}
DT = ['Physical', 'Vision', 'Listening', 'Speech impairment', 'Intellectual', 'Multidimensional']
YEARS = list(range(2021, 2027))
MIG_C = ['Loss of livelihood (loss of employment/business)', 'Decrease or decrease in income', 'Crop loss/damage', 'Damage to houses/displacement',
         'Debt Stress', 'Food insecurity', 'Education', 'Marriage/Family Reasons']
MIG_CL = ['Loss of livelihood', 'Fall in income', 'Crop loss', 'House damage', 'Debt stress', 'Food insecurity', 'Education', 'Marriage / family']
MIG_T = ['Seasonal', 'Cyclical', 'Long-term', 'Permanent']
MIG_TL = ['Seasonal', 'Cyclical', 'Long-term', 'Permanent']
MIG_D = ['Inside the village', 'Inside the Union/Upazila', 'Within the District', 'Outside the district', 'Urban areas (city)', 'International/Overseas']
MIG_DL = ['Same village', 'Same union / upazila', 'Same district', 'Other district', 'City', 'Overseas']
MIG_R = ['Flood', 'Cyclone', 'River erosion', 'Drought', 'Tidal surges/tidal waters', 'Increased salinity']
MIG_RL = ['Flood', 'Cyclone', 'River erosion', 'Drought', 'Tidal surge', 'Salinity']
CM_C = ['Poverty', 'Loss of income/livelihood due to climate disaster', 'Leaving school', 'Safety concerns', 'Social/family pressures',
        'Dowry-related reasons', 'Displacement/river erosion', 'Food Crisis', 'Debt Burden', 'Other (specify):']
CM_CL = ['Poverty', 'Climate income loss', 'Leaving school', 'Safety concerns', 'Social / family pressure', 'Dowry', 'Displacement / erosion',
         'Food crisis', 'Debt burden', 'Other']


def num(s): return pd.to_numeric(s, errors='coerce')


def flag(df, prefix, opt):
    c = [x for x in df.columns if x.startswith(prefix) and x.endswith('/' + opt)]
    return num(df[c[0]]).fillna(0).astype(int).clip(0, 1) if c else pd.Series(0, index=df.index)


def load(north_xlsx, south_xlsx):
    HH, EV, MEM, GEO = [], [], [], []
    for reg, f, code in [('Northern', north_xlsx, 'N'), ('Southern', south_xlsx, 'S')]:
        x = pd.read_excel(f, sheet_name=None)
        k = list(x)
        m = x[k[0]]
        mem = next(v for kk, v in x.items() if 'member' in kk.lower())
        d = next(v for kk, v in x.items() if 'disaster' in kk.lower())
        m = m[m["Respondent's Consent"] == 'Agreed'].copy()
        keep = set(m['_index'])
        m['HH_ID'] = [f'{code}-{int(i):05d}' for i in m['_index']]
        idmap = dict(zip(m['_index'], m['HH_ID']))
        h = pd.DataFrame({'HH_ID': m['HH_ID'].values}, index=m.index)
        h['Region'] = reg
        h['District'] = m['Select District'].fillna('Not stated')
        h['HeadSex'] = m['A9 Head of Sex'].map({'Male': 'Male', 'Women': 'Female', 'Other': 'Other'}).fillna('Not stated')
        h['FHH'] = (h['HeadSex'] == 'Female').astype(int)
        b2 = 'B2. Have you received any support from any project in your family in the last 5 years?'
        h['Gov'] = flag(m, b2, 'Government Assistance'); h['FS'] = flag(m, b2, 'Friendship Support')
        h['NGO'] = flag(m, b2, 'Support to other NGOs'); h['NoSupport'] = flag(m, b2, "Didn't get any help")
        h['AnySupport'] = ((h.Gov + h.FS + h.NGO) > 0).astype(int)
        h['CropValNormal'] = num(m['E7. Estimated Market Value (in normal year) (BDT)']).fillna(0)
        hd = (m['E16. Does this family currently have any outstanding debts?'] == 'Yes').astype(int)
        h['HasDebt'] = hd
        h['Debt'] = (num(m['E16.1. If the answer is yes, the amount of loan taken from institutional sources (Rs.)']).fillna(0)
                     + num(m['E16.4. Amount of Loan Taken from Non-Informal Sources (Rs.)']).fillna(0)) * hd
        for i, p in enumerate(PURP): h[f'P{i+1}'] = flag(m, 'E17. Purpose of Borrowing', p) * hd
        h['Mahajan'] = flag(m, 'E16.5. Sources of Informal Credit', 'Mahajan (High Interest Informal)') * hd
        h['Chronic'] = (m['B4. Members with chronic diseases (e.g. diabetes, high blood pressure, heart disease, asthma)'] == 'Yes').astype(int)
        h['MealsLow'] = m['G4. Average number of meals per day: Women'].isin(['1 time', '2 times']).astype(int)
        wl = (m['F5. Does waterlogging form in or around your home during heavy rains or floods?'] == 'Yes').astype(int)
        h['WL_Mosq'] = flag(m, 'F7. What are the common problems', 'Mosquito infestations/diseases') * wl
        h['WL_Contam'] = flag(m, 'F7. What are the common problems', 'Contamination of drinking water') * wl
        h['WL_Latrine'] = flag(m, 'F7. What are the common problems', 'Latrine overflow / sanitation issues') * wl
        h['Submit'] = pd.to_datetime(m['_submission_time']).dt.normalize()
        # migration (C block)
        h['Mig'] = (m['C1. Has any of your family members moved temporarily/permanently?'] == 'Yes').astype(int).values
        for k, c in [('MigN', 'C3. Number of Members Transferred: Total'), ('MigM', 'Number of Transferred Members: Male'),
                     ('MigW', 'Number of Transferred Members: Women'), ('MigC', 'Number of Transferred Members: Children (<18)')]:
            h[k] = (num(m[c]).fillna(0).clip(0, 30) * h['Mig']).values
        for i, c in enumerate(MIG_C): h[f'MC{i+1}'] = flag(m, 'C5. The main causes of migration', c).values * h['Mig'].values
        c4 = m['C4. Types of transfers'].fillna('')
        for i, t in enumerate(MIG_T): h[f'MT{i+1}'] = c4.str.contains(t, regex=False).astype(int).values * h['Mig'].values
        c6 = m['C6. The destination of the transfer'].fillna('')
        for i, t in enumerate(MIG_D): h[f'MD{i+1}'] = c6.str.contains(t, regex=False).astype(int).values * h['Mig'].values
        for i, t in enumerate(MIG_R): h[f'MR{i+1}'] = flag(m, 'C2. What are the reasons for which you have been relocated?', t).values * h['Mig'].values
        h['MigClim'] = (h[[f'MR{i+1}' for i in range(len(MIG_R))]].sum(axis=1) > 0).astype(int)
        HH.append(h.reset_index(drop=True))
        g = pd.DataFrame({'District': m['Select District'], 'lat': num(m['_A13. GPS coordinates_latitude']), 'lon': num(m['_A13. GPS coordinates_longitude'])})
        GEO.append(g[(g.lat.between(20.5, 26.7)) & (g.lon.between(88, 92.7))])

        d = d[d['_parent_index'].isin(keep)].copy()
        e = pd.DataFrame({'HH_ID': d['_parent_index'].map(idmap).values})
        e['Region'] = reg
        e['Type'] = d['D6. Types of disasters occurred'].fillna('Other').values
        e['Date'] = pd.to_datetime(d['D7. Month and year of disaster'], errors='coerce').values
        cols = {'Deaths': 'D9. Number of deaths', 'Injured': 'D10. Number of people injured',
                'HouseLoss': 'D11. Amount of damage due to house collapse in disaster (Rs)', 'HouseRepair': 'D12. Cost of repair/construction of the house (BDT)',
                'LatLoss': 'D13. Amount of damage due to broken latrine in disaster (BDT)', 'TWLoss': 'D15. Amount of damage due to failure of tubewell in disaster (Rs.)'}
        for kk, c in cols.items(): e[kk] = num(d[c]).fillna(0).clip(lower=0).values
        cp = [c for c in d.columns if 'Crop damage (what percentage)' in c][0]
        e['CropPct'] = num(d[cp]).values
        e['LivN'] = num(d['D21. No. of Livestock Loss and Death']).fillna(0).values
        e['LivV'] = num(d['D21.1 Approximate value of dead or lost cattle (in Rs.)']).fillna(0).values
        e['PouN'] = num(d['D22. Number of poultry losses and deaths']).fillna(0).values
        e['PouV'] = num(d['D22.1 Estimated value of dead or lost ducks/chickens (in IND)']).fillna(0).values
        for i, a in enumerate(ASSETS): e[f'A{i+1}'] = flag(d, 'D19. Property completely damaged (above 70%)', a).values
        EV.append(e)

        mm = mem[mem['_parent_index'].isin(keep)].copy()
        q = pd.DataFrame({'HH_ID': mm['_parent_index'].map(idmap).values})
        q['Female'] = (mm['Gender'] == 'Women').astype(int).values
        dis = mm['Disability'].fillna('There are no handicaps').str.replace('intellectual', 'Intellectual')
        q['DisType'] = dis.where(dis != 'There are no handicaps', '').values
        cm = (mm['Was this family member married before the age of 18?'] == 'Yes').astype(int)
        clim = (flag(mm, 'Causes of Child Marriage:', 'Loss of income/livelihood due to climate disaster') |
                flag(mm, 'Causes of Child Marriage:', 'Displacement/river erosion'))
        q['CMClim'] = (clim & cm).astype(int).values
        q['CM'] = cm.values
        q['CMAsk'] = mm['Was this family member married before the age of 18?'].isin(['Yes', 'No']).astype(int).values
        for i, c in enumerate(CM_C): q[f'CC{i+1}'] = (flag(mm, 'Causes of Child Marriage:', c) & cm).astype(int).values
        MEM.append(q)
    hh = pd.concat(HH, ignore_index=True)
    ev = pd.concat(EV, ignore_index=True)
    mem = pd.concat(MEM, ignore_index=True)
    geo = pd.concat(GEO, ignore_index=True)
    return hh, ev, mem, geo


def clean_events(ev, hh, P):
    ev = ev.merge(hh[['HH_ID', 'Submit', 'CropValNormal']], on='HH_ID', how='left')
    y = ev.Date.dt.year
    ev['InWin'] = ((y >= P['win_start']) & (y <= P['win_end']) & (ev.Date <= ev.Submit)).astype(int)
    pct = ev.CropPct.where((ev.CropPct >= 0) & (ev.CropPct <= P['max_crop_pct']), 0).fillna(0)
    ev['CropLoss'] = np.where(ev.CropValNormal <= P['max_crop_val'], ev.CropValNormal * pct / 100, 0)
    with np.errstate(divide='ignore', invalid='ignore'):
        ev['LivLoss'] = np.where((ev.LivN > 0) & (ev.LivV / ev.LivN <= P['max_liv_per']), ev.LivV, 0)
        ev['PouDied'] = np.where(ev.PouN <= P['max_pou_n'], ev.PouN, 0)
        ev['PouLoss'] = np.where((ev.PouN > 0) & (ev.PouDied > 0) & (ev.PouV / ev.PouN <= P['max_pou_per']), ev.PouV, 0)
    ev['LivDied'] = ev.LivN
    # Drought is slow-onset: injuries, deaths and structural damage recorded against it are treated as entry errors
    if P.get('drought_physical_exclude'):
        dr = ev.Type == 'Drought'
        ev['DroughtFlag'] = (dr & ((ev.Deaths + ev.Injured + ev.HouseLoss + ev.HouseRepair + ev.LatLoss + ev.TWLoss) > 0)).astype(int)
        for c in ['Deaths', 'Injured', 'HouseLoss', 'HouseRepair', 'LatLoss', 'TWLoss']: ev.loc[dr, c] = 0
    else:
        ev['DroughtFlag'] = 0
    ev['Infra'] = ev.HouseLoss + ev.LatLoss + ev.TWLoss
    ev['Livelihood'] = ev.CropLoss + ev.LivLoss + ev.PouLoss
    ev['Total'] = ev.Infra + ev.Livelihood
    ev['Year'] = ev.Date.dt.year
    return ev


SUMC = ['HouseLoss', 'HouseRepair', 'LatLoss', 'TWLoss', 'CropLoss', 'LivLoss', 'PouLoss', 'Infra', 'Livelihood', 'Total',
        'Deaths', 'Injured', 'LivDied', 'PouDied'] + [f'A{i+1}' for i in range(12)]


def hh_roll(hh, ev_scope):
    g = ev_scope.groupby('HH_ID')
    s = g[SUMC].sum()
    s['Events'] = g.size()
    out = hh.set_index('HH_ID').join(s).fillna({c: 0 for c in SUMC + ['Events']})
    for i in range(12): out[f'F{i+1}'] = (out[f'A{i+1}'] > 0).astype(int)
    out['AnyFull'] = (out[[f'F{i+1}' for i in range(12)]].sum(axis=1) > 0).astype(int)
    out['Affected'] = (out.Events > 0).astype(int)
    return out


def corr(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    if n < 3 or x.std() == 0 or y.std() == 0: return None
    r = float(np.corrcoef(x, y)[0, 1])
    t = r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
    p = float(2 * stats.t.sf(abs(t), n - 2))
    return [round(r, 3), round(p, 4), n]


def R(v, d=0):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))): return None
    return round(float(v), d) if d else int(round(float(v)))


def region_metrics(H, E_scope, E_win, M, P):
    """H: rolled households (filtered), E_scope: events in scope for those HHs, E_win: events in window (any type) for those HHs"""
    n = len(H)
    if n < P['min_cell']:
        return {'n': n, 'suppressed': True}
    A = H[H.Affected == 1]
    pct = lambda s: R(s.mean() * 1000) / 1000 if len(s) else 0
    mean = lambda s: R(s.mean()) if len(s) else 0
    low = lambda s: R(s[s >= P['min_low']].min()) if (s >= P['min_low']).any() else 0
    o = {'n': n, 'affected': int(A.shape[0]), 'pct_affected': pct(H.Affected)}
    for c in ['Total', 'Infra', 'Livelihood', 'HouseLoss', 'LatLoss', 'TWLoss', 'CropLoss', 'LivLoss', 'PouLoss', 'Deaths', 'Injured', 'LivDied', 'PouDied', 'HouseRepair']:
        o[c] = R(H[c].sum())
    o['avg_affected'] = mean(A.Total)
    o['per_hh_year'] = R(H.Total.sum() / n / P['years'])
    o['any_full'] = pct(H.AnyFull)
    o['any_full_n'] = int(H.AnyFull.sum())
    sup, nos = H[H.AnySupport == 1], H[H.AnySupport == 0]
    o['support'] = {'yes': {'n': len(sup), 'total': R(sup.Total.sum()), 'avg': mean(sup.Total), 'avg_affected': mean(sup.Total[sup.Affected == 1]), 'infra': R(sup.Infra.sum()), 'liv': R(sup.Livelihood.sum())},
                    'no': {'n': len(nos), 'total': R(nos.Total.sum()), 'avg': mean(nos.Total), 'avg_affected': mean(nos.Total[nos.Affected == 1]), 'infra': R(nos.Infra.sum()), 'liv': R(nos.Livelihood.sum())},
                    'gov': {'n': int(H.Gov.sum()), 'avg': mean(H.Total[H.Gov == 1])}, 'fs': {'n': int(H.FS.sum()), 'avg': mean(H.Total[H.FS == 1])}}
    o['assets'] = [pct(H[f'F{i+1}']) for i in range(12)]
    o['range'] = {c: [low(H[c]), R(H[c].max())] for c in ['Infra', 'Livelihood', 'Total', 'HouseLoss']}
    o['hh_with'] = {c: int((H[c] > 0).sum()) for c in ['Infra', 'Livelihood', 'CropLoss', 'LivLoss', 'PouLoss', 'Deaths', 'Injured']}
    cyc = E_win[E_win.Type == 'Storms/cyclones']
    o['cyclone'] = [mean(cyc.HouseLoss[cyc.HouseLoss > 0]), mean(cyc.HouseRepair[cyc.HouseRepair > 0]), int((cyc.HouseLoss > 0).sum())]
    # breakdowns
    def ev_break(E, key, cats):
        g = E.groupby(key)
        res = {}
        for m in ['Total', 'Infra', 'Livelihood', 'Deaths', 'Injured', 'LivDied', 'PouDied']:
            s = g[m].sum()
            res[m] = [R(s.get(c, 0) / (1e6 if m in ('Total', 'Infra', 'Livelihood') else 1), 2 if m in ('Total', 'Infra', 'Livelihood') else 0) for c in cats]
        res['Count'] = [int(g.size().get(c, 0)) for c in cats]
        return res
    o['by_type'] = ev_break(E_win, 'Type', TYPES)
    o['by_year'] = ev_break(E_scope, 'Year', YEARS)
    dd = {}
    for m in ['Total', 'Infra', 'Livelihood', 'Deaths', 'Injured', 'LivDied', 'PouDied']:
        s = H.groupby('District')[m].sum()
        dd[m] = [R(s.get(c, 0) / (1e6 if m in ('Total', 'Infra', 'Livelihood') else 1), 2 if m in ('Total', 'Infra', 'Livelihood') else 0) for c in DISTRICTS['Northern'] + DISTRICTS['Southern']]
    s = H.groupby('District')['Affected'].sum()
    dd['Count'] = [int(s.get(c, 0)) for c in DISTRICTS['Northern'] + DISTRICTS['Southern']]
    o['by_district'] = dd
    # correlations
    HL = H[(H.HouseLoss + H.HouseRepair) > 0]
    cy2 = cyc[(cyc.HouseLoss + cyc.HouseRepair) > 0]
    pairs = [(H.Gov, H.Total), (H.FS, H.Total), (H.NoSupport, H.Total), (H.FHH, H.Total), (H.FHH, H.AnySupport),
             (HL.HouseLoss, HL.HouseRepair), (cy2.HouseLoss, cy2.HouseRepair), (H.HouseLoss, H.Debt), (H.CropLoss, H.Debt),
             (H.Total, H.Debt), (H.Total, H.P4)]
    o['corr'] = [corr(a, b) for a, b in pairs]
    o['groups'] = [[mean(H.Total[H[c] == 1]), mean(H.Total[H[c] == 0]), int((H[c] == 1).sum())] for c in ['Gov', 'FS', 'NoSupport', 'FHH']]
    F, Mh = H[H.FHH == 1], H[H.FHH == 0]
    o['fhh'] = {'n': len(F), 'support': pct(F.AnySupport), 'support_m': pct(Mh.AnySupport), 'avg': mean(F.Total), 'avg_m': mean(Mh.Total), 'nosupport': pct(F.NoSupport)}
    # women / health / debt
    Ma = M[M.HH_ID.isin(A.index)]
    fem = Ma[Ma.Female == 1]
    o['women'] = {'in_hh': int(H.Women.sum()), 'in_affected': int(A.Women.sum()), 'disabled': int((fem.DisType != '').sum()),
                  'cm_climate': int(fem.CMClim.sum()), 'fhh_affected': int(A.FHH.sum()),
                  'dis_types': [int((fem.DisType == t).sum()) for t in DT]}
    Mig = H[H.Mig == 1]
    o['mig'] = {'hh': int(H.Mig.sum()), 'pct': pct(H.Mig), 'members': R(H.MigN.sum()), 'male': R(H.MigM.sum()), 'women': R(H.MigW.sum()),
                'child': R(H.MigC.sum()), 'clim': int(H.MigClim.sum()), 'causes': [int(H[f'MC{i+1}'].sum()) for i in range(len(MIG_C))],
                'types': [int(H[f'MT{i+1}'].sum()) for i in range(len(MIG_T))], 'dest': [int(H[f'MD{i+1}'].sum()) for i in range(len(MIG_D))],
                'reasons': [int(H[f'MR{i+1}'].sum()) for i in range(len(MIG_R))]}
    Mh_all = M[M.HH_ID.isin(H.index)]
    ask = int(Mh_all.CMAsk.sum()); yes = int(Mh_all.CM.sum())
    o['cm'] = {'asked': ask, 'yes': yes, 'pct': R(yes / ask * 1000) / 1000 if ask else 0, 'climate': int(Mh_all.CMClim.sum()),
               'causes': [int(Mh_all[f'CC{i+1}'].sum()) for i in range(len(CM_C))]}
    o['health'] = [pct(A[c]) for c in ['Chronic', 'WL_Mosq', 'WL_Contam', 'WL_Latrine', 'MealsLow', 'P2']]
    o['debt'] = {'pct': pct(H.HasDebt), 'avg': mean(H.Debt[H.HasDebt == 1]), 'total': R(H.Debt.sum()), 'mahajan': int(H.Mahajan.sum()),
                 'loan_repair_damaged': int(((H.P4 == 1) & (H.HouseLoss > 0)).sum()), 'food_affected': int(((H.P1 == 1) & (H.Affected == 1)).sum()),
                 'care_affected': int(((H.P2 == 1) & (H.Affected == 1)).sum()), 'purpose': [int(H[f'P{i+1}'].sum()) for i in range(8)],
                 'avg_damaged': mean(H.Debt[H.HouseLoss > 0]), 'avg_undamaged': mean(H.Debt[H.HouseLoss == 0])}
    return o


def build(north_xlsx, south_xlsx, P=PARAMS):
    hh, ev, mem, geo = load(north_xlsx, south_xlsx)
    ev = clean_events(ev, hh, P)
    women = mem.groupby('HH_ID').Female.sum()
    hh['Women'] = hh.HH_ID.map(women).fillna(0).astype(int)
    evw = ev[ev.InWin == 1]
    dlist = ['All'] + DISTRICTS['Northern'] + DISTRICTS['Southern']
    slist = ['All', 'Male', 'Female', 'Other']
    tlist = ['All'] + TYPES
    rolled_cache = {}
    combos = {}
    for t in tlist:
        es = evw if t == 'All' else evw[evw.Type == t]
        rolled = hh_roll(hh, es)
        rolled_cache[t] = rolled
        for d, s in itertools.product(dlist, slist):
            Hf = rolled
            if d != 'All': Hf = Hf[Hf.District == d]
            if s != 'All': Hf = Hf[Hf.HeadSex == s]
            ids = set(Hf.index)
            key = f'{d}|{s}|{t}'
            out = {}
            for rk, rv in [('N', 'Northern'), ('S', 'Southern'), ('A', None)]:
                Hr = Hf if rv is None else Hf[Hf.Region == rv]
                rid = set(Hr.index)
                out[rk] = region_metrics(Hr, es[es.HH_ID.isin(rid)], evw[evw.HH_ID.isin(rid)], mem, P)
            combos[key] = out
    centroids = {dname: [round(float(g.lat.median()), 2), round(float(g.lon.median()), 2)] for dname, g in geo.groupby('District')}
    excluded = {'outside_window': int((ev.InWin == 0).sum()),
                'crop_pct_invalid': int(((ev.CropPct > P['max_crop_pct']) | (ev.CropPct < 0)).sum()),
                'poultry_value_outliers': int(((ev.PouV > 0) & (ev.PouLoss == 0)).sum()),
                'drought_physical': int(ev.DroughtFlag.sum()),
                'livestock_value_outliers': int(((ev.LivV > 0) & (ev.LivLoss == 0)).sum())}
    meta = {'updated': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), 'households': {'Northern': int((hh.Region == 'Northern').sum()), 'Southern': int((hh.Region == 'Southern').sum())},
            'events': int(len(ev)), 'members': int(len(mem)), 'params': P, 'excluded': excluded,
            'lists': {'district': dlist, 'sex': slist, 'type': tlist, 'types': TYPES, 'years': YEARS, 'districts': DISTRICTS,
                      'assets': ALAB, 'purpose': PLAB, 'dis_types': DT,
                      'mig_causes': MIG_CL, 'mig_types': MIG_TL, 'mig_dest': MIG_DL, 'mig_reasons': MIG_RL, 'cm_causes': CM_CL}, 'centroids': centroids,
            'district_n': {k: int(v) for k, v in hh.District.value_counts().items()}}
    return {'meta': meta, 'data': combos}


if __name__ == '__main__':
    import sys
    out = build(sys.argv[1], sys.argv[2])
    s = json.dumps(out, separators=(',', ':'))
    open(sys.argv[3], 'w').write(s)
    print('wrote', sys.argv[3], f'{len(s)/1e6:.2f} MB')
