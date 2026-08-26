# Sydney Housing Price Prediction and Decision Support System

Predicts residential sale price from observable listing characteristics for three contrasting Sydney suburbs (Blacktown, Chatswood, Mosman), and serves the trained model through a small web application.


## Layout

| Path | Contents |
|---|---|
| `data/sydney_housing.csv` | Collected dataset, **239 sold properties × 39 columns** |
| `data/raw_cache.tar.gz` | The 31 raw pages the dataset was built from |
| `data/collection_log.json`, `audit_crosscheck.json` | Collection provenance and integrity check |
| `data/data_dictionary.md` | Column definitions |
| `notebooks/lab.ipynb` | The analysis: filtering, EDA, modelling, failure analysis, deployment |
| `src/build_dataset.py` | Rebuilds `sydney_housing.csv` from the raw pages |
| `src/audit_crosscheck.py` | Cross-checks index pages against listing pages |
| `src/app.py` | Streamlit application |
| `src/model.joblib` | Trained pipeline, written by the notebook |
| `report/` | LaTeX sources and compiled PDF |

## Setup

```bash
pip install -r requirements.txt
```

## Reproducing the results

Run the notebook top to bottom:

```bash
jupyter notebook notebooks/lab.ipynb          # or:
jupyter nbconvert --to notebook --execute --inplace notebooks/lab.ipynb
```

## Rebuilding the dataset from raw pages (optional)

```bash
mkdir -p data/raw && tar -xzf data/raw_cache.tar.gz -C data/raw
python src/build_dataset.py
```

This regenerates `data/sydney_housing.csv` (239 rows) and `data/collection_log.json`. It is idempotent, meaning that the output matches the committed file.

## Running the application

```bash
streamlit run src/app.py        # serves http://localhost:8501
```

Requires `src/model.joblib`, which the notebook produces. The app takes fields readable off a listing (suburb, property type, bedrooms, bathrooms, car spaces, area, sale date, and optionally the description) and returns an estimated sale price with a ±20% band.

Two tabs are provided: **Single property** for one estimate, and **Upload CSV** for batch
estimates over a file with columns `suburb, property_type, bedrooms, bathrooms, parking,
area_sqm, sold_date`.
