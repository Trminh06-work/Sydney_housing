
import joblib, numpy as np, pandas as pd, streamlit as st
from pathlib import Path

st.set_page_config(page_title="Sydney House Price Estimator", page_icon="house")
B = joblib.load(Path(__file__).parent / "model.joblib")
pipe, NUM, CAT = B["pipeline"], B["num"], B["cat"]

st.title("Sydney House Price Estimator")
st.caption(f"SIT307 prototype — {B['model_name']}, trained on {B['trained_rows']} "
           "sold properties in Blacktown, Chatswood and Mosman")

EPOCH = pd.Timestamp("2026-01-01")

def build(suburb, ptype, beds, baths, parking, area, when, desc=""):
    """Recreate the engineered feature row from raw listing inputs."""
    is_unit = int(ptype != "House")
    row = {c: 0 for c in NUM}
    row.update({
        # 0 or blank means "not known": pass NaN so the pipeline's median
        # imputer handles it exactly as it did during training.
        "area_sqm": float(area) if area and float(area) > 0 else np.nan,
        "bedrooms": beds, "bathrooms": baths, "parking": parking,
        "bed_bath": beds + .5*baths, "beds_x_unit": beds*is_unit, "is_unit": is_unit,
        "t": (pd.Timestamp(when) - EPOCH).days,
        "month": pd.Timestamp(when).month,
    })
    for c in NUM:                       # kw_* flags, same rule as engineer()
        if c.startswith("kw_"):
            row[c] = int(c[3:] in desc.lower())
    row.update({"suburb": suburb, "property_type": ptype, "sale_method": "Private treaty"})
    return pd.DataFrame([row])[NUM + CAT]

tab1, tab2 = st.tabs(["Single property", "Upload CSV"])

with tab1:
    c1, c2 = st.columns(2)
    suburb  = c1.selectbox("Suburb", B["suburbs"])
    ptype   = c2.selectbox("Property type", ["House","Apartment","Townhouse",
                                             "Semi-detached","Villa","Retirement living"])
    beds    = c1.number_input("Bedrooms", 0, 10, 3)
    baths   = c2.number_input("Bathrooms", 0, 10, 2)
    parking = c1.number_input("Car spaces", 0, 10, 1)
    area    = c2.number_input("Area m2 (0 = not known)", 0, 5000, 0, 10)
    when    = c1.date_input("Sale date", pd.Timestamp("2026-08-01"))
    desc    = st.text_area("Listing description (optional)", height=80)

    if st.button("Estimate", type="primary"):
        p = float(np.exp(pipe.predict(build(suburb, ptype, beds, baths,
                                            parking, area, when, desc))[0]))
        st.metric("Estimated sale price", f"${p:,.0f}")
        st.info(f"Indicative range +/-20%: ${p*0.8:,.0f} to ${p*1.2:,.0f}  "
                f"(held-out MAPE {B['test_mape']:.1f}%)")
        if suburb == "Mosman" and p > 3e6:
            st.warning("High-value Mosman property. The model cannot see harbour outlook, "
                       "aspect or build quality — treat this as a floor, not a valuation.")
        if area == 0:
            st.warning("No area supplied. The model substitutes the training median "
                       "and the estimate is correspondingly less specific.")
        if ptype != "House" and beds <= 1:
            st.warning("One-bedroom units were the model's largest failure case: position and "
                       "outlook dominate their price and are not in the feature set.")

with tab2:
    up = st.file_uploader("CSV: suburb, property_type, bedrooms, bathrooms, parking, "
                          "area_sqm, sold_date", type="csv")
    if up:
        d = pd.read_csv(up)
        X = pd.concat([build(r.suburb, r.property_type, r.bedrooms, r.bathrooms,
                             r.parking, r.area_sqm, r.sold_date)
                       for r in d.itertuples()], ignore_index=True)
        d["estimated_price"] = np.exp(pipe.predict(X)).round(0)
        st.dataframe(d)
        st.download_button("Download", d.to_csv(index=False), "estimates.csv")
