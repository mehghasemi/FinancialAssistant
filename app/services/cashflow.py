"""Cash movements use settlement dates; planning continues to use due dates."""
from datetime import timedelta
import jdatetime
from ..calendar import format_jalali_date, jalali_month_bounds, jalali_month_label
from ..database import connection


def cash_overview(month, today):
    start, end = (day.isoformat() for day in jalali_month_bounds(month))
    cutoff = today.isoformat()
    with connection() as db:
        opening_row = db.execute("SELECT amount,as_of_date FROM cash_opening WHERE id=1").fetchone()
        opening = dict(opening_row) if opening_row else None
        accounts = [dict(row) for row in db.execute("SELECT id,opening_amount,opening_date FROM accounts")]
        account_mode = any(row["opening_date"] for row in accounts)
        if account_mode:
            complete = all(row["opening_date"] for row in accounts)
            opening = dict(amount=sum(row["opening_amount"] for row in accounts), as_of_date=accounts[0]["opening_date"]) if complete else None
        events = [dict(row) for row in db.execute("""SELECT id,title,transaction_type AS kind,
            amount,account_id,COALESCE(settled_on,occurred_on) AS date,occurred_on AS due_date,
            'transaction' AS source, NULL AS commitment_id,settled_date_assumed AS assumed
            FROM transactions WHERE status='paid' AND payment_id IS NULL""")]
        events.extend(dict(row) for row in db.execute("""SELECT p.id,c.title,'installment' AS kind,
            p.amount,p.account_id,p.paid_on AS date,i.due_date,'payment' AS source,i.commitment_id,0 AS assumed
            FROM payments p JOIN installments i ON i.id=p.installment_id
            JOIN commitments c ON c.id=i.commitment_id"""))
    # Future-dated entries do not increase today's available money.
    events = sorted((item for item in events if item["date"] <= cutoff), key=lambda item:(item["date"],item["source"],item["id"]))

    def net(items):
        return sum(item["amount"] if item["kind"]=="income" else -item["amount"] for item in items)

    def balance(until):
        if not opening or until <= opening["as_of_date"]:
            return None
        return opening["amount"] + net(item for item in events if opening["as_of_date"] <= item["date"] < until)

    account_balances = {row["id"]: row["opening_amount"] + net(item for item in events if item["account_id"] == row["id"] and item["date"] >= row["opening_date"]) if row["opening_date"] else None for row in accounts}

    period = [item for item in events if start <= item["date"] < end]
    arrears = [item for item in period if item["kind"] != "income" and item["due_date"] < start]
    income = sum(item["amount"] for item in period if item["kind"]=="income")
    paid = sum(item["amount"] for item in period if item["kind"]!="income")
    components = dict(current=0, arrears=0, advance=0)
    for item in period:
        if item["kind"] != "income":
            key = "arrears" if item["due_date"] < start else "advance" if item["due_date"] >= end else "current"
            components[key] += item["amount"]
    current_year = jdatetime.date.fromgregorian(date=today).year
    annual = []
    for number in range(1,13):
        key = f"{current_year}-{number:02d}"
        first,last = (day.isoformat() for day in jalali_month_bounds(key))
        rows = [item for item in events if first <= item["date"] < last]
        future = first > cutoff
        annual.append(dict(month=key,label=jalali_month_label(key),future=future,
                           income=None if future else sum(item["amount"] for item in rows if item["kind"]=="income"),
                           paid=None if future else sum(item["amount"] for item in rows if item["kind"]!="income"),
                           balance=None if future else balance(min(last,(today+timedelta(days=1)).isoformat()))))
    cash_items = [item for item in events if opening and item["date"] >= opening["as_of_date"]]

    def display(items):
        return [{**item, "date":format_jalali_date(item["date"]), "due_date":format_jalali_date(item["due_date"])} for item in items]

    return dict(account_mode=account_mode, account_balances=account_balances, unassigned_count=sum(item["account_id"] is None for item in events), income=income, paid=paid, net=income-paid, arrears_paid=sum(item["amount"] for item in arrears),
                available=balance((today+timedelta(days=1)).isoformat()),
                as_of=format_jalali_date(today), opening={**opening,"as_of_date":format_jalali_date(opening["as_of_date"])} if opening else None,
                assumed_dates=sum(bool(item["assumed"]) for item in events),
                period_items=display(period), arrears_items=display(arrears), cash_items=display(cash_items),
                cash_income=sum(item["amount"] for item in cash_items if item["kind"]=="income"),
                cash_paid=sum(item["amount"] for item in cash_items if item["kind"]!="income"),
                components=components, annual=annual, year=current_year)
