import pandas as pd
import plotly.express as px
from django.shortcuts import render
from django.http import JsonResponse
import pickle
import os

# Path to store uploaded DataFrame temporarily
DF_FILE = "uploaded_df.pkl"


def dashboard_view(request):
    message = "Upload a data file to get started."
    df_all_html = None
    line_chart_html = None
    payee_options = []

    if request.method == "POST" and request.FILES.get("data_file"):
        # Read uploaded Excel or CSV
        df = (
            pd.read_excel(request.FILES["data_file"])
            if request.FILES["data_file"].name.endswith(".xlsx")
            else pd.read_csv(request.FILES["data_file"])
        )
        df.columns = df.columns.str.strip()

        # Save DataFrame for later use
        pickle.dump(df, open(DF_FILE, "wb"))

        # Convert to HTML for overview display
        df_all_html = df.to_html(
            classes="table table-striped table-hover", index=False, escape=False
        )

        # Prepare interactive trend chart for first numeric column
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if numeric_cols and "payout_date" in df.columns:
            df["payout_date"] = pd.to_datetime(df["payout_date"], errors="coerce")
            trend_df = (
                df.groupby(df["payout_date"].dt.to_period("M"))[numeric_cols[0]]
                .sum()
                .reset_index()
            )
            trend_df["month"] = trend_df["payout_date"].astype(str)
            fig = px.line(trend_df, x="month", y=numeric_cols[0], title="Trend Chart")
            line_chart_html = fig.to_html(full_html=False)

        # Extract Payee IDs
        if "Payee ID" in df.columns:
            payee_options = list(df["Payee ID"].dropna().astype(str).unique())

        message = "Data uploaded successfully."

    return render(
        request,
        "dashboard/dashboard.html",
        {
            "message": message,
            "df_all_html": df_all_html,
            "line_chart_html": line_chart_html,
            "payee_options": payee_options,
        },
    )


def generate_amortization(request):
    """Generates amortization schedule with dynamic prediction calculator."""
    payee_id = request.GET.get("payee_id")
    total_incentive = request.GET.get("total_incentive")
    cap_percent = request.GET.get("cap_percent")
    term = request.GET.get("term")
    payment_start_date = request.GET.get("payment_start_date")

    if not payee_id:
        return JsonResponse({"status": "error", "message": "No Payee ID provided."})

    # Load uploaded DataFrame
    if not os.path.exists(DF_FILE):
        return JsonResponse(
            {"status": "error", "message": "No data available. Please upload a file first."}
        )

    df = pickle.load(open(DF_FILE, "rb"))

    # Validate Payee
    df_payee = df[df["Payee ID"].astype(str) == payee_id]
    if df_payee.empty:
        return JsonResponse({"status": "error", "message": "Payee not found."})

    # Get user inputs or fallback to defaults
    total_incentive = (
        float(total_incentive)
        if total_incentive
        else float(df_payee["Total Incentive"].iloc[0])
    )
    cap_percent = (
        float(cap_percent)
        if cap_percent
        else float(df_payee.get("Cap %", pd.Series([100])).iloc[0])
    )
    term = (
        int(term)
        if term
        else int(df_payee.get("Term", pd.Series([12])).iloc[0])
    )
    payment_start_date = (
        pd.to_datetime(payment_start_date)
        if payment_start_date
        else pd.to_datetime(
            df_payee.get("Payment Start Date", pd.Series([pd.Timestamp.today()])).iloc[0]
        )
    )

    # Calculate amortization
    payout_freq = "Monthly"
    freq_map = {"Monthly": 1, "Quarterly": 3, "Semi-Annually": 6, "Annually": 12}
    freq_months = freq_map[payout_freq]
    periods = int(term / freq_months)
    capped_total = total_incentive * cap_percent / 100
    payment_amount = capped_total / periods

    schedule = []
    current_date = payment_start_date
    for i in range(1, periods + 1):
        schedule.append(
            [i, current_date.date(), round(payment_amount, 2)]
        )
        current_date += pd.DateOffset(months=freq_months)

    df_amort = pd.DataFrame(schedule, columns=["Installment #", "Payment Date", "Payment Amount"])
    html = df_amort.to_html(classes="table table-striped table-hover", index=False)

    return JsonResponse(
        {
            "status": "success",
            "html": html,
            "summary": {
                "Payee ID": payee_id,
                "Total Incentive": round(total_incentive, 2),
                "Cap %": round(cap_percent, 2),
                "Term (Months)": term,
                "Total Payout": round(df_amort["Payment Amount"].sum(), 2),
                "Payment Start Date": str(payment_start_date.date()),
            },
        }
    )
