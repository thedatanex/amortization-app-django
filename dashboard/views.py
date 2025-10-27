import pandas as pd
import plotly.express as px
from django.shortcuts import render
from django.http import JsonResponse
import pickle
import os
from django.views.decorators.http import require_GET
from sklearn.ensemble import IsolationForest
from scipy import stats
import numpy as np
import plotly.graph_objs as go
from datetime import datetime
from django.http import JsonResponse

# Temporary file to hold uploaded data
DF_FILE = "uploaded_df.pkl"

# =====================  DASHBOARD MAIN VIEW  =====================

def dashboard_view(request):
    message = "Upload a data file to get started."
    df_all_html = None
    line_chart_html = None
    payee_options = []

    if request.method == "POST" and request.FILES.get("data_file"):
        df = (
            pd.read_excel(request.FILES["data_file"])
            if request.FILES["data_file"].name.endswith(".xlsx")
            else pd.read_csv(request.FILES["data_file"])
        )
        df.columns = df.columns.str.strip()
        pickle.dump(df, open(DF_FILE, "wb"))

        df_all_html = df.to_html(classes="table table-striped table-hover", index=False, escape=False)

        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if numeric_cols and "payout_date" in df.columns:
            df["payout_date"] = pd.to_datetime(df["payout_date"], errors="coerce")
            trend_df = (
                df.groupby(df["payout_date"].dt.to_period("M"))[numeric_cols[0]].sum().reset_index()
            )
            trend_df["month"] = trend_df["payout_date"].astype(str)
            fig = px.line(trend_df, x="month", y=numeric_cols[0], title="Trend Chart")
            line_chart_html = fig.to_html(full_html=False)

        if "Payee ID" in df.columns:
            payee_options = list(df["Payee ID"].dropna().astype(str).unique())

        message = "Data uploaded successfully."

    return render(
        request,
        "dashboard/dashboard.html",
        {"message": message, "df_all_html": df_all_html, "line_chart_html": line_chart_html, "payee_options": payee_options},
    )


# =====================  SINGLE PAYEE AMORTIZATION  =====================

def generate_amortization(request):
    payee_id = request.GET.get("payee_id")
    total_incentive = request.GET.get("total_incentive")
    cap_percent = request.GET.get("cap_percent")
    term = request.GET.get("term")
    payment_start_date = request.GET.get("payment_start_date")

    if not payee_id:
        return JsonResponse({"status": "error", "message": "No Payee ID provided."})
    if not os.path.exists(DF_FILE):
        return JsonResponse({"status": "error", "message": "No data available. Please upload a file first."})

    df = pickle.load(open(DF_FILE, "rb"))
    df_payee = df[df["Payee ID"].astype(str) == payee_id]
    if df_payee.empty:
        return JsonResponse({"status": "error", "message": "Payee not found."})

    total_incentive = float(total_incentive or df_payee["Total Incentive"].iloc[0])
    cap_percent = float(cap_percent or df_payee.get("Cap %", pd.Series([100])).iloc[0])
    term = int(term or df_payee.get("Term", pd.Series([12])).iloc[0])
    payment_start_date = pd.to_datetime(
        payment_start_date or df_payee.get("Payment Start Date", pd.Series([pd.Timestamp.today()])).iloc[0]
    )

    payout_freq = "Monthly"
    freq_months = {"Monthly": 1, "Quarterly": 3, "Semi-Annually": 6, "Annually": 12}[payout_freq]
    periods = int(term / freq_months)
    capped_total = total_incentive * cap_percent / 100
    payment_amount = capped_total / periods

    schedule = []
    current_date = payment_start_date
    for i in range(1, periods + 1):
        schedule.append([i, current_date.date(), round(payment_amount, 2)])
        current_date += pd.DateOffset(months=freq_months)

    df_amort = pd.DataFrame(schedule, columns=["Installment #", "Payment Date", "Payment Amount"])
    html = df_amort.to_html(classes="table table-striped table-hover", index=False)

    return JsonResponse({
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
    })


# =====================  MULTIPLE PAYEES AMORTIZATION  =====================

def generate_amortization_multiple(request):
    payee_ids = request.GET.getlist("payee_ids[]")
    cap_percent = request.GET.get("cap_percent")
    term = request.GET.get("term")
    payment_start_date = request.GET.get("payment_start_date")

    if not payee_ids:
        return JsonResponse({"status": "error", "message": "No Payee IDs provided."})
    if not os.path.exists(DF_FILE):
        return JsonResponse({"status": "error", "message": "No data available. Please upload a file first."})

    df = pickle.load(open(DF_FILE, "rb"))
    result = []

    for payee_id in payee_ids:
        df_payee = df[df["Payee ID"].astype(str) == payee_id]
        if df_payee.empty:
            continue

        total_incentive = float(df_payee["Total Incentive"].iloc[0])
        cap = float(cap_percent or df_payee.get("Cap %", pd.Series([100])).iloc[0])
        term_months = int(term or df_payee.get("Term", pd.Series([12])).iloc[0])
        start_date = pd.to_datetime(
            payment_start_date or df_payee.get("Payment Start Date", pd.Series([pd.Timestamp.today()])).iloc[0]
        )

        freq_months = 1
        periods = int(term_months / freq_months)
        capped_total = total_incentive * cap / 100
        payment_amount = capped_total / periods

        schedule = []
        current_date = start_date
        for i in range(1, periods + 1):
            schedule.append([i, current_date.date(), round(payment_amount, 2)])
            current_date += pd.DateOffset(months=freq_months)

        df_amort = pd.DataFrame(schedule, columns=["Installment #", "Payment Date", "Payment Amount"])
        result.append({
            "payee_id": payee_id,
            "schedule_html": df_amort.to_html(classes="table table-striped table-hover", index=False)
        })

    return JsonResponse({"status": "success", "data": result})

# =====================  AI GET FRAUD DATA  =====================

def get_fraud_data(request):
    data = {
        "labels": ["TXN1","TXN2","TXN3","TXN4"],
        "scores": [0.1,0.8,0.3,0.95],
        "records": [
            {"transaction_id":"TXN1","payee":"EMP-101","amount":1000,"anomaly_score":0.1,"flagged":"No"},
            {"transaction_id":"TXN2","payee":"EMP-102","amount":5000,"anomaly_score":0.8,"flagged":"Yes"},
            {"transaction_id":"TXN3","payee":"EMP-103","amount":750,"anomaly_score":0.3,"flagged":"No"},
            {"transaction_id":"TXN4","payee":"EMP-104","amount":1200,"anomaly_score":0.95,"flagged":"Yes"},
        ]
    }
    return JsonResponse(data)

# =====================  AI FRAUD & ANOMALY DETECTION  =====================

@require_GET
def detect_anomalies(request):
    if not os.path.exists(DF_FILE):
        return JsonResponse({"status": "error", "message": "No data available. Upload a file first."})

    try:
        df = pickle.load(open(DF_FILE, "rb"))
    except Exception as e:
        return JsonResponse({"status": "error", "message": f"Failed to read data: {e}"})

    candidate_cols = [c for c in df.columns if any(k in c.lower() for k in ["payment", "payout", "amount", "incentive"])]
    amount_col = next((c for c in candidate_cols if pd.api.types.is_numeric_dtype(df[c])), None)
    if not amount_col:
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if not numeric_cols:
            return JsonResponse({"status": "error", "message": "No numeric column found for anomaly detection."})
        amount_col = numeric_cols[0]

    work = df.copy()
    work["_amount"] = pd.to_numeric(work[amount_col], errors="coerce")
    work = work.dropna(subset=["_amount"]).reset_index(drop=True)

    X = work[["_amount"]].values
    iso = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
    iso_preds = iso.fit_predict(X)
    iso_scores = -iso.decision_function(X)
    z_scores = np.abs(stats.zscore(work["_amount"].values))
    combined_flag = (iso_preds == -1) | (z_scores > 3.0)

    work["_is_anomaly"] = combined_flag
    work["_iso_score"] = iso_scores
    work["_z_score"] = z_scores

    anomalies = work[work["_is_anomaly"]]
    anomalies_html = (
        "<p>No anomalies detected.</p>"
        if anomalies.empty
        else anomalies.to_html(classes="table table-striped table-sm", index=False, float_format="%.2f")
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(y=work["_amount"], mode="lines+markers", name="Payouts"))
    if not anomalies.empty:
        fig.add_trace(go.Scatter(
            x=anomalies.index, y=anomalies["_amount"], mode="markers",
            name="Anomalies", marker=dict(color="red", size=10, symbol="x")
        ))
    fig.update_layout(title="AI-based Fraud & Anomaly Detection", xaxis_title="Index", yaxis_title=amount_col)
    chart_html = fig.to_html(full_html=False)

    summary = {"total_rows": len(work), "anomalies_detected": len(anomalies), "amount_column": amount_col}

    return JsonResponse({"status": "success", "summary": summary, "chart_html": chart_html, "anomalies_html": anomalies_html})
