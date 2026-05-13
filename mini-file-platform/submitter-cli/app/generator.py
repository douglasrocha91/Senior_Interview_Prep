import csv
import random
from datetime import date, timedelta
from pathlib import Path

_CURRENCIES = ["USD", "EUR", "BRL", "GBP", "JPY"]
_DESCRIPTIONS = [
    "Business lunch",
    "Taxi fare",
    "Hotel stay",
    "Conference registration",
    "Office supplies",
    "Flight ticket",
    "Client dinner",
    "Parking fee",
    "Team event",
    "Software subscription",
]
_COLUMNS = ["record_id", "expense_date", "employee_id", "currency", "amount", "description"]


def generate_csv(output_path: Path, rows: int = 50, partner: str = "acme") -> Path:
    """Write a sample expense CSV to *output_path* and return the path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today()

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_COLUMNS)
        writer.writeheader()
        for i in range(1, rows + 1):
            writer.writerow({
                "record_id": f"{partner.upper()}-{i:05d}",
                "expense_date": (today - timedelta(days=random.randint(0, 30))).isoformat(),
                "employee_id": f"EMP-{random.randint(1000, 9999)}",
                "currency": random.choice(_CURRENCIES),
                "amount": round(random.uniform(5.0, 500.0), 2),
                "description": random.choice(_DESCRIPTIONS),
            })

    return output_path
