"""
SmartServe - café decision dashboard.
Run with:  streamlit run app.py
Needs transactions_clean.csv and inventory.csv in the same folder
(or upload your own files from the sidebar).
"""
from itertools import combinations
from collections import Counter

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st

st.set_page_config(page_title="SmartServe", page_icon="☕", layout="wide")

TX_COLS = {"order_id", "date", "hour", "weekday", "product", "category",
           "quantity", "unit_price", "revenue"}
INV_COLS = {"product", "avg_daily_sales", "reorder_level", "current_stock"}
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday"]


# ---------------------------------------------------------------- loading
def load_csv(source, required, label):
    """Read a CSV and check it has the columns the app needs."""
    try:
        df = pd.read_csv(source)
    except FileNotFoundError:
        st.error(f"Could not find {label}. Put it in the app folder or upload it.")
        st.stop()
    except Exception as e:
        st.error(f"Could not read {label}: {e}")
        st.stop()
    missing = required - set(df.columns)
    if missing:
        st.error(f"{label} is missing columns: {', '.join(sorted(missing))}")
        st.stop()
    return df


# ---------------------------------------------------------------- analysis
def top_pairs(tx, n=10):
    """Count how often two products appear in the same order."""
    counts = Counter()
    for _, items in tx.groupby("order_id")["product"].unique().items():
        if len(items) > 1:
            counts.update(combinations(sorted(items), 2))
    out = pd.DataFrame(
        [(a, b, c) for (a, b), c in counts.most_common(n)],
        columns=["Product A", "Product B", "Orders together"])
    return out


def stock_status(inv):
    inv = inv.copy()
    inv["days_of_stock"] = (inv["current_stock"] / inv["avg_daily_sales"]).round(1)

    def label(r):
        if r["current_stock"] < r["reorder_level"]:
            return "Reorder now"
        if r["days_of_stock"] > 6:
            return "Overstocked"
        return "OK"

    inv["status"] = inv.apply(label, axis=1)
    return inv


def build_recommendations(tx, inv_status, pairs):
    recs = []
    # 1. Reorder alerts
    for _, r in inv_status[inv_status["status"] == "Reorder now"].iterrows():
        recs.append(("Inventory",
                     f"Reorder {r['product']}: only {r['current_stock']} left "
                     f"(about {r['days_of_stock']} days of sales; reorder level is "
                     f"{r['reorder_level']})."))
    # 2. Overstock
    for _, r in inv_status[inv_status["status"] == "Overstocked"].iterrows():
        recs.append(("Inventory",
                     f"{r['product']} is overstocked ({r['days_of_stock']} days of stock). "
                     f"Reduce the next order or run a small offer."))
    # 2b. Low performers among regular items
    regular = tx[tx["product"].isin(inv_status["product"])]
    low = regular.groupby("product")["revenue"].sum().nsmallest(3).index
    for p in low:
        recs.append(("Low performer",
                     f"{p} is one of the weakest regular sellers. Promote it with a "
                     f"best-seller or review whether to keep stocking it."))
    # 3. Combo offers
    for _, r in pairs.head(3).iterrows():
        recs.append(("Offers",
                     f"{r['Product A']} + {r['Product B']} are bought together in "
                     f"{r['Orders together']} orders. Try a combo offer."))
    # 4. Peak hours for the top products
    top = tx.groupby("product")["quantity"].sum().nlargest(3).index
    for p in top:
        h = tx[tx["product"] == p].groupby("hour")["quantity"].sum().idxmax()
        recs.append(("Preparation",
                     f"{p} sells most around {h}:00. Have extra ready before then."))
    return recs


# ---------------------------------------------------------------- sidebar
st.sidebar.title("☕ SmartServe")
st.sidebar.caption("Upload your own files or use the sample data.")
tx_file = st.sidebar.file_uploader("Sales data (CSV)", type="csv")
inv_file = st.sidebar.file_uploader("Inventory data (CSV)", type="csv")

tx = load_csv(tx_file or "transactions_clean.csv", TX_COLS, "sales data")
inv = load_csv(inv_file or "inventory.csv", INV_COLS, "inventory data")
tx["date"] = pd.to_datetime(tx["date"], errors="coerce")
tx = tx.dropna(subset=["date"])

cats = sorted(tx["category"].unique())
chosen = st.sidebar.multiselect("Categories", cats, default=cats)
tx = tx[tx["category"].isin(chosen)]
# Keep a separate dataset for monthly/yearly analysis
tx_analysis = tx.copy()
if tx.empty:
    st.warning("No data for the selected categories.")
    st.stop()

# Date filter


# Date filter
min_date = tx["date"].min().date()
max_date = tx["date"].max().date()

date_range = st.date_input(
    "Select analysis period",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

# Handle both a single date and a date range
if isinstance(date_range, (tuple, list)):
    if len(date_range) == 2:
        start_date, end_date = date_range
    elif len(date_range) == 1:
        start_date = end_date = date_range[0]
    else:
        start_date, end_date = min_date, max_date
else:
    start_date = end_date = date_range

tx = tx[
    (tx["date"].dt.date >= start_date)
    & (tx["date"].dt.date <= end_date)
]

if tx.empty:
    st.warning(
        "No sales data is available for this date range. "
        "Please select a different period."
    )
    st.stop()



if tx.empty:
    st.warning(
        "No sales data is available for this date range. "
        "Please select a different period."
    )
    st.stop()

st.title("SmartServe: café decision dashboard")
st.caption(f"{tx['date'].min():%d %b %Y} to {tx['date'].max():%d %b %Y}  |  "
           "Sales are real; prices and inventory are assumed/simulated.")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1 Sales",
    "2 Customer behaviour",
    "3 Inventory",
    "4 Recommendations",
    "5 Monthly & Yearly Analysis"
])

# ---------------------------------------------------------------- 1 Sales
with tab1:
    orders = tx["order_id"].nunique()
    revenue = tx["revenue"].sum()
    peak_hour = tx.groupby("hour")["order_id"].nunique().idxmax()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total revenue", f"₹{revenue:,.0f}")
    c2.metric("Orders", f"{orders:,}")
    c3.metric("Avg order value", f"₹{revenue / orders:,.0f}")
    c4.metric("Peak hour", f"{peak_hour}:00–{peak_hour + 1}:00")

    left, right = st.columns(2)
    with left:
        st.subheader("Top products by revenue")
        top = tx.groupby("product")["revenue"].sum().nlargest(10).sort_values()
        fig, ax = plt.subplots(figsize=(6, 4))
        top.plot.barh(ax=ax, color="#4c78a8")
        ax.set_xlabel("Revenue (₹)")
        ax.set_ylabel("")
        st.pyplot(fig)
    with right:
        st.subheader("Revenue by category")
        cat = tx.groupby("category")["revenue"].sum().sort_values()
        fig, ax = plt.subplots(figsize=(6, 4))
        cat.plot.barh(ax=ax, color="#f58518")
        ax.set_xlabel("Revenue (₹)")
        ax.set_ylabel("")
        st.pyplot(fig)

    st.subheader("Daily revenue trend")
    daily = tx.groupby("date")["revenue"].sum()
    fig, ax = plt.subplots(figsize=(12, 3.5))
    ax.plot(daily.index, daily.values, color="#4c78a8", linewidth=1, alpha=0.5,
            label="Daily")
    ax.plot(daily.index, daily.rolling(7).mean(), color="#e45756", linewidth=2,
            label="7-day average")
    ax.set_ylabel("Revenue (₹)")
    ax.legend()
    st.pyplot(fig)

    st.subheader("Weekly revenue")
    weekly = tx.set_index("date")["revenue"].resample("W").sum()
    fig, ax = plt.subplots(figsize=(12, 3.2))
    ax.bar(weekly.index, weekly.values, width=5, color="#4c78a8")
    ax.set_ylabel("Revenue (₹)")
    st.pyplot(fig)
    st.caption("The first and last weeks are partial, so they look lower.")

    st.subheader("Product performance")
    perf = (tx.groupby(["product", "category"])
              .agg(units_sold=("quantity", "sum"), revenue=("revenue", "sum"))
              .reset_index().sort_values("revenue", ascending=False))
    perf["revenue_share_%"] = (perf["revenue"] / perf["revenue"].sum() * 100).round(1)
    left, right = st.columns(2)
    with left:
        st.markdown("**Best performers (top 10 by revenue)**")
        st.dataframe(perf.head(10), hide_index=True, width="stretch")
    with right:
        st.markdown("**Low performers (bottom 10 by revenue)**")
        st.dataframe(perf.tail(10).sort_values("revenue"), hide_index=True,
                     width="stretch")
    with st.expander("See every product"):
        st.dataframe(perf, hide_index=True, width="stretch")

# ---------------------------------------------------- 2 Customer behaviour
with tab2:
    st.subheader("When do customers buy? (orders by weekday and hour)")
    heat = (tx.groupby(["weekday", "hour"])["order_id"].nunique()
              .unstack(fill_value=0).reindex(DAY_ORDER))
    heat = heat.loc[:, (heat.columns >= 8) & (heat.columns <= 18)]
    fig, ax = plt.subplots(figsize=(12, 4))
    sns.heatmap(
    heat.fillna(0).astype(int),
    cmap="YlOrRd",
    annot=True,
    fmt="d",
    ax=ax,
    cbar=False
)
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("")
    st.pyplot(fig)

    st.subheader("Order value patterns")
    ov = tx.groupby("order_id").agg(value=("revenue", "sum"),
                                    items=("quantity", "sum"),
                                    products=("product", "nunique"))
    m1, m2, m3 = st.columns(3)
    m1.metric("Median order value", f"₹{ov['value'].median():,.0f}")
    m2.metric("Avg items per order", f"{ov['items'].mean():.1f}")
    m3.metric("Orders with 2+ different products", f"{(ov['products'] > 1).mean():.0%}")
    fig, ax = plt.subplots(figsize=(12, 3.2))
    ax.hist(ov["value"].clip(upper=ov["value"].quantile(0.99)), bins=30,
            color="#4c78a8")
    ax.set_xlabel("Order value (₹), top 1% grouped into the last bar")
    ax.set_ylabel("Orders")
    st.pyplot(fig)

    left, right = st.columns(2)
    with left:
        st.subheader("Orders by weekday")
        wd = tx.groupby("weekday")["order_id"].nunique().reindex(DAY_ORDER)
        fig, ax = plt.subplots(figsize=(6, 3.5))
        wd.plot.bar(ax=ax, color="#4c78a8")
        ax.set_xlabel("")
        ax.set_ylabel("Orders")
        st.pyplot(fig)
    with right:
        st.subheader("Often bought together")
        pairs = top_pairs(tx)
        st.dataframe(pairs, hide_index=True, width="stretch")

# ------------------------------------------------------------ 3 Inventory
inv_status = stock_status(inv)
pairs = top_pairs(tx)
with tab3:
    st.subheader("Stock vs demand")
    n_low = (inv_status["status"] == "Reorder now").sum()
    n_high = (inv_status["status"] == "Overstocked").sum()
    c1, c2 = st.columns(2)
    c1.metric("Items to reorder now", int(n_low))
    c2.metric("Overstocked items", int(n_high))

    colours = {"Reorder now": "#e45756", "Overstocked": "#f2a93b", "OK": "#54a24b"}
    plot = inv_status.sort_values("days_of_stock")
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(plot["product"], plot["days_of_stock"],
            color=plot["status"].map(colours))
    ax.set_xlabel("Days of stock left (current stock / average daily sales)")
    st.pyplot(fig)

    show = inv_status.sort_values("status")[
        ["product", "avg_daily_sales", "current_stock", "reorder_level",
         "days_of_stock", "status"]]
    st.dataframe(show, hide_index=True, width="stretch")

# ------------------------------------------------------- 4 Recommendations
with tab4:
    st.subheader("What the owner can do")
    recs = build_recommendations(tx, inv_status, pairs)
    for kind, text in recs:
        st.markdown(f"**{kind}:** {text}")
    st.caption("Recommendations come from simple rules on sales, combinations "
               "and stock levels, not from a prediction model.")
    
# -------------------------------------------------------
# 5 Monthly & Yearly Analysis
# -------------------------------------------------------

# -------------------------------------------------------
# 5 Monthly & Yearly Business Analysis
# -------------------------------------------------------

with tab5:

    st.header("Monthly & Yearly Business Analysis")
    st.write("Select a month or year to generate a complete business report.")

    # Use all dates, independent of the main date filter
    data = tx_analysis.copy()

    # First selection: Monthly or Yearly
    analysis_type = st.radio(
        "Choose analysis type",
        ["Monthly Analysis", "Yearly Analysis"],
        horizontal=True
    )

    # SECOND SELECTION: MONTH
    if analysis_type == "Monthly Analysis":

        available_months = sorted(
            data["date"].dt.to_period("M").unique(),
            reverse=True
        )

        selected_month = st.selectbox(
            "Select Month",
            available_months,
            format_func=lambda x: x.strftime("%B %Y")
        )

        period_data = data[
            data["date"].dt.to_period("M") == selected_month
        ].copy()

        report_name = selected_month.strftime("%B %Y")

    # SECOND SELECTION: YEAR
    else:

        available_years = sorted(
            data["date"].dt.year.unique(),
            reverse=True
        )

        selected_year = st.selectbox(
            "Select Year",
            available_years
        )

        period_data = data[
            data["date"].dt.year == selected_year
        ].copy()

        report_name = str(selected_year)

    # COMPLETE BUSINESS REPORT
    st.divider()
    st.subheader(f"Business Analysis: {report_name}")

    # 1. KEY PERFORMANCE INDICATORS
    revenue = period_data["revenue"].sum()
    orders = period_data["order_id"].nunique()
    units = period_data["quantity"].sum()
    avg_order = revenue / orders if orders else 0

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total Revenue", f"₹{revenue:,.0f}")
    c2.metric("Total Orders", f"{orders:,}")
    c3.metric("Units Sold", f"{units:,}")
    c4.metric("Average Order Value", f"₹{avg_order:,.0f}")

    # 2. PRODUCT PERFORMANCE
    st.subheader("1. Product Performance")

    products = (
        period_data.groupby("product")
        .agg(
            Revenue=("revenue", "sum"),
            Units_Sold=("quantity", "sum")
        )
        .sort_values("Revenue", ascending=False)
    )

    left, right = st.columns(2)

    with left:
        st.write("Top 5 Products")
        st.dataframe(products.head(5), width="stretch")

    with right:
        st.write("Bottom 5 Products")
        st.dataframe(
            products.tail(5).sort_values("Revenue"),
            width="stretch"
        )

    # 3. CATEGORY PERFORMANCE
    st.subheader("2. Category Performance")

    category_sales = (
        period_data.groupby("category")["revenue"]
        .sum()
        .sort_values(ascending=False)
    )

    st.bar_chart(category_sales)

    # 4. CUSTOMER BEHAVIOUR
    st.subheader("3. Customer Behaviour")

    order_analysis = period_data.groupby("order_id").agg(
        Items=("quantity", "sum"),
        Products=("product", "nunique"),
        Order_Value=("revenue", "sum")
    )

    a, b, c = st.columns(3)

    a.metric(
        "Average Items per Order",
        f"{order_analysis['Items'].mean():.1f}"
    )

    b.metric(
        "Multiple Product Orders",
        f"{(order_analysis['Products'] > 1).mean():.1%}"
    )

    c.metric(
        "Median Order Value",
        f"₹{order_analysis['Order_Value'].median():,.0f}"
    )

    # 5. SALES PATTERNS
    st.subheader("4. Sales Patterns")

    left, right = st.columns(2)

    with left:
        st.write("Revenue by Weekday")

        weekday_sales = (
            period_data.groupby("weekday")["revenue"]
            .sum()
            .reindex(DAY_ORDER)
        )

        st.bar_chart(weekday_sales)

    with right:
        st.write("Revenue by Hour")

        hourly_sales = (
            period_data.groupby("hour")["revenue"]
            .sum()
        )

        st.bar_chart(hourly_sales)

    # 6. BUSINESS INSIGHTS
    st.subheader("5. SmartServe Business Suggestions")

    if not products.empty:

        best_product = products["Revenue"].idxmax()
        worst_product = products["Revenue"].idxmin()

        st.success(
            f"{best_product} generated the highest product revenue "
            f"during {report_name}."
        )

        st.info(
            f"{worst_product} generated the lowest product revenue. "
            "Review its demand and consider a promotion."
        )

    if not category_sales.empty:

        best_category = category_sales.idxmax()

        st.info(
            f"{best_category} was the highest revenue-generating category."
        )

    if not hourly_sales.empty:

        peak_hour = hourly_sales.idxmax()

        st.success(
            f"Your highest revenue hour was around {peak_hour}:00. "
            "Consider preparing sufficient stock before this period."
        )

    # 7. PERIOD-SPECIFIC REVENUE TREND
    st.subheader("6. Revenue Trend")

    if analysis_type == "Monthly Analysis":

        daily_sales = (
            period_data.groupby(
                period_data["date"].dt.day
            )["revenue"].sum()
        )

        st.bar_chart(daily_sales)

        st.caption("Daily revenue for the selected month.")

    else:

        monthly_sales = (
            period_data.groupby(
                period_data["date"].dt.month
            )["revenue"].sum()
        )

        monthly_sales.index = [
            pd.Timestamp(
                year=selected_year,
                month=int(month),
                day=1
            ).strftime("%B")
            for month in monthly_sales.index
        ]

        st.bar_chart(monthly_sales)

        st.caption("Monthly revenue breakdown for the selected year.")

    # 8. DOWNLOAD REPORT
    st.subheader("7. Download Report")

    csv_report = period_data.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download Selected Period Data",
        data=csv_report,
        file_name=f"SmartServe_{report_name.replace(' ', '_')}.csv",
        mime="text/csv"
    )

    st.caption(
        "All figures are calculated from the selected categories "
        "and the complete available date range in the sales CSV."
    )

