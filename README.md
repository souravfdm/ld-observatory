# Friendship Loss & Damage Observatory: live web dashboard

A free website that refreshes itself every morning from KoboToolbox.
Only anonymised totals are published: no names, NID numbers, phone numbers, GPS points or household records.
Any filter combination with fewer than 5 households is hidden.

```
docs/index.html            the website (filters, tabs, charts, map)
docs/data.json             aggregated figures (rebuilt daily)
scripts/ld_pipeline.py     cleaning rules + indicator calculations
scripts/update.py          downloads both Kobo projects and rebuilds data.json
.github/workflows/update.yml   runs update.py every day at 06:17 Dhaka time
```

## One-time setup (about 20 minutes)

### 1. Put the files on GitHub
1. Create a free account at https://github.com (use a Friendship email if possible).
2. Click **New repository**, name it `ld-observatory`, choose **Public**, and click **Create repository**.
3. Click **uploading an existing file** and drag in **everything inside this folder** (including the `.github` folder). Click **Commit changes**.
   - If `.github` does not upload, click **Add file → Create new file**, type `.github/workflows/update.yml` as the name, and paste the contents of that file.

### 2. Turn on the website
**Settings → Pages →** Source: *Deploy from a branch*, Branch: `main`, Folder: `/docs` → **Save**.
After a minute the site is live at `https://YOUR-USERNAME.github.io/ld-observatory/`.

### 3. Prepare a Kobo export in each project (North and South)
In KoboToolbox open the project → **DATA → Downloads**:
- Select export type: **XLS**
- Value and header format: **English (en)** labels
- Advanced options: **Export Select Many questions as single and separate columns**, **Include data from all versions** ticked, **Include groups in headers** *not* ticked
- **Save selection as…** `dashboard` → **Export**

Then get the link: open `https://kf.kobotoolbox.org/api/v2/assets/ASSET_UID/export-settings/` in your browser while logged in to Kobo
(ASSET_UID is the code in the project's URL, e.g. `.../forms/aBcD123.../`). Copy the `data_url_xlsx` value of the `dashboard` export.
If you use the EU server, replace `kf.` with `eu.`.

### 4. Add three secrets in GitHub
**Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|---|---|
| `KOBO_TOKEN` | Kobo **Account settings → Security → API key** |
| `KOBO_NORTH_URL` | `data_url_xlsx` of the North project |
| `KOBO_SOUTH_URL` | `data_url_xlsx` of the South project |

Secrets stay hidden; they are never shown on the website or in the code.

### 5. First refresh
**Actions → Update dashboard data → Run workflow**. When it turns green, reload your site.
From then on it updates automatically every morning. You can press *Run workflow* any time for an instant refresh.

## Adding your own domain later
1. Buy the domain (e.g. `ldobservatory.org`).
2. GitHub: **Settings → Pages → Custom domain**, type `www.ldobservatory.org`, **Save**, tick **Enforce HTTPS**.
3. At the domain seller's DNS page add a **CNAME** record: name `www` → value `YOUR-USERNAME.github.io`.
   For the bare domain add four **A** records to 185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153.

## Changing rules
Cleaning thresholds, the exchange rate (124 BDT/US$) and the recall window are in `PARAMS` at the top of `scripts/ld_pipeline.py`.

## If something stops
- A red ❌ in **Actions** means the download failed. The site keeps showing the last good data. Open the run to read the message (usually an expired API key or a changed export).
- GitHub pauses scheduled jobs in repositories with no activity for 60 days. If that happens, open **Actions** and click **Enable workflow**.
- Before making the site public, confirm with Friendship management (and IIED where relevant) that these aggregated figures can be shared.
