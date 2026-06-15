from __future__ import annotations

import base64
import io
import json
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


SETTINGS_FILE = Path(__file__).with_name("settings.json")
APP_VERSION = "1.2.2"
APP_REPOSITORY_URL = "https://github.com/johnmburke/Amortization_App"
APP_VERSION_URLS = [
    "https://raw.githubusercontent.com/johnmburke/Amortization_App/main/version.json",
    "https://raw.githubusercontent.com/johnmburke/Amortization_App/refs/heads/main/version.json",
    "https://api.github.com/repos/johnmburke/Amortization_App/contents/version.json?ref=main",
]
APP_ARCHIVE_URL = (
    "https://github.com/johnmburke/Amortization_App/archive/refs/heads/main.zip"
)
APP_UPDATE_FILES = {"app.py", "requirements.txt", "version.json"}
DEFAULT_SCHEDULE_NAME = "Default"
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
SCHEDULE_FIELDS = {
    "current_balance",
    "monthly_interest_rate_percent",
    "escrow_payment",
    "is_mortgage_loan",
    "payment_amounts_raw",
    "max_months",
    "start_month",
    "start_year",
    "remembered_extra_payments",
    "recurring_extra_payment",
    "recurring_extra_payments",
}


@dataclass(frozen=True)
class AmortizationSummary:
    monthly_payment: float
    escrow_payment: float
    total_monthly_payment: float
    recurring_extra_payment: float
    recurring_extra_start_date: date | None
    total_recurring_extra_paid: float
    months_to_payoff: int | None
    final_payment_date: date | None
    total_interest_paid: float
    total_escrow_paid: float
    total_paid: float
    final_balance: float
    status: str


def parse_payment_amounts(raw_value: str) -> list[float]:
    values: list[float] = []

    for part in raw_value.replace("\n", ",").split(","):
        cleaned = part.strip().replace("$", "").replace(",", "")
        if cleaned:
            values.append(float(cleaned))

    return sorted(set(values))


def load_settings() -> dict[str, object]:
    if not SETTINGS_FILE.exists():
        return {}

    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as settings_file:
            settings = json.load(settings_file)
    except (OSError, json.JSONDecodeError):
        return {}

    return settings if isinstance(settings, dict) else {}


def save_settings(settings: dict[str, object]) -> None:
    with SETTINGS_FILE.open("w", encoding="utf-8") as settings_file:
        json.dump(settings, settings_file, indent=2)


def version_parts(version: str) -> tuple[int, ...]:
    parts: list[int] = []

    for part in version.split("."):
        digits = "".join(character for character in part if character.isdigit())
        parts.append(int(digits or 0))

    return tuple(parts)


def compare_versions(current_version: str, latest_version: str) -> int:
    current_parts = list(version_parts(current_version))
    latest_parts = list(version_parts(latest_version))
    max_length = max(len(current_parts), len(latest_parts))
    current_parts.extend([0] * (max_length - len(current_parts)))
    latest_parts.extend([0] * (max_length - len(latest_parts)))

    if current_parts < latest_parts:
        return -1
    if current_parts > latest_parts:
        return 1
    return 0


def fetch_url_bytes(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"AmortizationCalculator/{APP_VERSION}"},
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


@st.cache_data(ttl=900, show_spinner=False)
def fetch_latest_app_version() -> dict[str, object]:
    errors: list[str] = []
    status_codes: list[int] = []

    for version_url in APP_VERSION_URLS:
        request = urllib.request.Request(
            version_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"AmortizationCalculator/{APP_VERSION}",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            errors.append(f"{version_url}: HTTP {error.code}")
            status_codes.append(error.code)
            continue
        except (
            OSError,
            TimeoutError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ) as error:
            errors.append(f"{version_url}: {error}")
            continue

        if "api.github.com/repos" in version_url:
            encoded_content = response_data.get("content", "")
            if response_data.get("encoding") == "base64" and encoded_content:
                try:
                    decoded_content = base64.b64decode(encoded_content).decode("utf-8")
                    version_info = json.loads(decoded_content)
                except (ValueError, json.JSONDecodeError) as error:
                    errors.append(f"{version_url}: {error}")
                    continue
            else:
                errors.append(f"{version_url}: version file content was not readable")
                continue
        else:
            version_info = response_data

        latest_version = version_info.get("version")
        if not isinstance(latest_version, str) or not latest_version.strip():
            return {
                "ok": False,
                "error": "GitHub version file does not include a version number.",
            }

        return {
            "ok": True,
            "version": latest_version.strip(),
            "download_url": str(version_info.get("download_url", APP_REPOSITORY_URL)),
            "archive_url": str(version_info.get("archive_url", APP_ARCHIVE_URL)),
            "release_notes": str(version_info.get("release_notes", "")),
        }

    if 404 in status_codes:
        return {
            "ok": False,
            "status_code": 404,
            "error": (
                "GitHub returned 404 for the update file. Confirm that the "
                "repository is public and that version.json exists on the main branch."
            ),
        }

    return {
        "ok": False,
        "error": "; ".join(errors) if errors else "No update source responded.",
    }


def install_app_update(archive_url: str) -> tuple[bool, str]:
    install_folder = Path(__file__).resolve().parent

    try:
        archive_bytes = fetch_url_bytes(archive_url)
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            archive_names = archive.namelist()
            updated_files = []

            for update_file in APP_UPDATE_FILES:
                matching_name = next(
                    (
                        archive_name
                        for archive_name in archive_names
                        if archive_name.endswith(f"/{update_file}")
                    ),
                    None,
                )
                if matching_name is None:
                    continue

                destination = install_folder / update_file
                destination.write_bytes(archive.read(matching_name))
                updated_files.append(update_file)
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        zipfile.BadZipFile,
    ) as error:
        return False, str(error)

    if "app.py" not in updated_files:
        return False, "The downloaded update did not include app.py."

    return True, f"Updated {', '.join(sorted(updated_files))}."


def render_update_checker() -> None:
    update_check = fetch_latest_app_version()
    if not update_check["ok"]:
        return

    latest_version = str(update_check["version"])
    if compare_versions(APP_VERSION, latest_version) >= 0:
        return

    archive_url = str(update_check["archive_url"])
    release_notes = str(update_check["release_notes"])

    with st.expander("Application Updates", expanded=True):
        st.warning(f"Version {latest_version} is available.")
        st.caption(f"Installed version: {APP_VERSION}")
        if release_notes:
            st.caption(release_notes)
        if st.button("Update", use_container_width=True):
            with st.spinner("Downloading and installing the update..."):
                update_installed, update_message = install_app_update(archive_url)

            if not update_installed:
                st.error("The update could not be installed.")
                st.caption(update_message)
                return

            fetch_latest_app_version.clear()
            st.session_state["update_message"] = update_message
            st.rerun()


def saved_float(
    settings: dict[str, object],
    key: str,
    default: float,
    minimum: float = 0.0,
) -> float:
    try:
        value = float(settings.get(key, default))
    except (TypeError, ValueError):
        return default

    return max(minimum, value)


def saved_int(
    settings: dict[str, object],
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(settings.get(key, default))
    except (TypeError, ValueError):
        return default

    return min(max(value, minimum), maximum)


def saved_text(settings: dict[str, object], key: str, default: str) -> str:
    value = settings.get(key, default)
    return value if isinstance(value, str) else default


def saved_bool(settings: dict[str, object], key: str, default: bool = False) -> bool:
    value = settings.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def saved_remembered_payments(settings: dict[str, object]) -> list[dict[str, object]]:
    payments = settings.get("remembered_extra_payments", [])
    if not isinstance(payments, list):
        return []

    remembered_payments: list[dict[str, object]] = []
    for payment in payments:
        if not isinstance(payment, dict):
            continue

        try:
            amount = float(payment.get("amount", 0.0))
        except (TypeError, ValueError):
            continue

        if amount > 0:
            remembered_payments.append(
                {
                    "amount": amount,
                    "saved_on": str(payment.get("saved_on", "")),
                }
            )

    return remembered_payments


def build_recurring_extra_payment(
    target_payment: float,
    amount: float,
    start_month: int,
    start_year: int,
) -> dict[str, int | float]:
    return {
        "target_payment": round(target_payment, 2),
        "amount": round(amount, 2),
        "start_month": min(max(start_month, 1), 12),
        "start_year": min(max(start_year, 1900), 2300),
    }


def recurring_extra_key(payment: dict[str, int | float]) -> str:
    return (
        f"{float(payment['target_payment']):.2f}|"
        f"{float(payment['amount']):.2f}|"
        f"{int(payment['start_year']):04d}-{int(payment['start_month']):02d}"
    )


def recurring_extra_label(payment: dict[str, int | float]) -> str:
    start_date = date(int(payment["start_year"]), int(payment["start_month"]), 1)
    return (
        f"{money(float(payment['amount']))}/mo from "
        f"{format_month_year(start_date)} on "
        f"{money(float(payment['target_payment']))}"
    )


def recurring_extra_header(payments: list[dict[str, int | float]]) -> str:
    if not payments:
        return "Additional Recurring Payments"

    first_payment = payments[0]
    start_date = date(
        int(first_payment["start_year"]),
        int(first_payment["start_month"]),
        1,
    )
    summary = (
        f"{money(float(first_payment['amount']))}/mo "
        f"from {format_month_year(start_date)}"
    )

    if len(payments) > 1:
        summary = f"{summary}, +{len(payments) - 1} more"

    return f"Additional Recurring Payments ({summary})"


def recurring_extras_for_payment(
    payments: list[dict[str, int | float]],
    target_payment: float,
) -> list[dict[str, int | float]]:
    return [
        payment
        for payment in payments
        if round(float(payment["target_payment"]), 2) == round(target_payment, 2)
    ]


def saved_recurring_extra_payments(
    settings: dict[str, object],
) -> list[dict[str, int | float]]:
    raw_payments = settings.get("recurring_extra_payments", [])
    payments: list[dict[str, int | float]] = []

    if isinstance(raw_payments, list):
        for payment in raw_payments:
            if not isinstance(payment, dict):
                continue

            try:
                target_payment = float(payment.get("target_payment", 0.0))
                amount = float(payment.get("amount", 0.0))
                start_month = int(payment.get("start_month", date.today().month))
                start_year = int(payment.get("start_year", date.today().year))
            except (TypeError, ValueError):
                continue

            if target_payment > 0 and amount > 0:
                payments.append(
                    build_recurring_extra_payment(
                        target_payment,
                        amount,
                        start_month,
                        start_year,
                    )
                )

    legacy_payment = settings.get("recurring_extra_payment", {})
    if isinstance(legacy_payment, dict):
        try:
            amount = float(legacy_payment.get("amount", 0.0))
            start_month = int(legacy_payment.get("start_month", date.today().month))
            start_year = int(legacy_payment.get("start_year", date.today().year))
            payment_amounts = parse_payment_amounts(
                saved_text(settings, "payment_amounts_raw", "")
            )
        except (TypeError, ValueError):
            amount = 0.0
            payment_amounts = []

        if amount > 0 and payment_amounts:
            payments.append(
                build_recurring_extra_payment(
                    payment_amounts[0],
                    amount,
                    start_month,
                    start_year,
                )
            )

    unique_payments: dict[str, dict[str, int | float]] = {}
    for payment in payments:
        unique_payments[recurring_extra_key(payment)] = payment

    return list(unique_payments.values())


def normalize_schedule_name(name: str) -> str:
    cleaned_name = name.strip()
    return cleaned_name if cleaned_name else DEFAULT_SCHEDULE_NAME


def get_saved_schedules(settings: dict[str, object]) -> dict[str, dict[str, object]]:
    schedules: dict[str, dict[str, object]] = {}
    raw_schedules = settings.get("saved_schedules", {})
    has_named_schedule_storage = isinstance(raw_schedules, dict)

    if has_named_schedule_storage:
        for name, schedule in raw_schedules.items():
            if isinstance(name, str) and isinstance(schedule, dict):
                schedules[normalize_schedule_name(name)] = schedule

    legacy_schedule = {
        key: settings[key]
        for key in SCHEDULE_FIELDS
        if key in settings
    }

    if (
        legacy_schedule
        and not has_named_schedule_storage
        and DEFAULT_SCHEDULE_NAME not in schedules
    ):
        schedules[DEFAULT_SCHEDULE_NAME] = legacy_schedule

    return schedules


def get_last_schedule_name(
    settings: dict[str, object],
    schedule_names: list[str],
) -> str | None:
    if not schedule_names:
        return None

    last_schedule_name = saved_text(settings, "last_schedule_name", schedule_names[0])
    if last_schedule_name in schedule_names:
        return last_schedule_name

    return schedule_names[0]


def save_named_schedule(
    settings: dict[str, object],
    schedule_name: str,
    schedule: dict[str, object],
) -> dict[str, object]:
    saved_schedules = get_saved_schedules(settings)
    clean_name = normalize_schedule_name(schedule_name)

    updated_settings = dict(settings)
    saved_schedules[clean_name] = schedule
    updated_settings["saved_schedules"] = saved_schedules
    updated_settings["last_schedule_name"] = clean_name

    # Keep top-level fields in place so older saved files still remain readable.
    updated_settings.update(schedule)
    return updated_settings


def delete_named_schedule(
    settings: dict[str, object],
    schedule_name: str,
) -> dict[str, object]:
    saved_schedules = get_saved_schedules(settings)
    clean_name = normalize_schedule_name(schedule_name)
    saved_schedules.pop(clean_name, None)

    updated_settings = dict(settings)
    updated_settings["saved_schedules"] = saved_schedules
    updated_settings["last_schedule_name"] = next(iter(saved_schedules), "")

    if clean_name == DEFAULT_SCHEDULE_NAME:
        for key in SCHEDULE_FIELDS:
            updated_settings.pop(key, None)

    return updated_settings


def add_months(start_date: date, months_to_add: int) -> date:
    month_index = start_date.month - 1 + months_to_add
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def format_month_year(value: date | None) -> str:
    return value.strftime("%b %Y") if value else "N/A"


def format_period(months: int | None) -> str:
    if months is None:
        return "N/A"

    years, remaining_months = divmod(months, 12)
    if years and remaining_months:
        return f"{years} yr {remaining_months} mo"
    if years:
        return f"{years} yr"
    return f"{remaining_months} mo"


def build_settings(
    current_balance: float,
    monthly_interest_rate_percent: float,
    escrow_payment: float,
    is_mortgage_loan: bool,
    payment_amounts_raw: str,
    max_months: int,
    start_month: int,
    start_year: int,
    remembered_extra_payments: list[dict[str, object]],
    recurring_extra_payments: list[dict[str, int | float]],
) -> dict[str, object]:
    return {
        "current_balance": current_balance,
        "monthly_interest_rate_percent": monthly_interest_rate_percent,
        "escrow_payment": escrow_payment,
        "is_mortgage_loan": is_mortgage_loan,
        "payment_amounts_raw": payment_amounts_raw,
        "max_months": max_months,
        "start_month": start_month,
        "start_year": start_year,
        "remembered_extra_payments": remembered_extra_payments,
        "recurring_extra_payments": recurring_extra_payments,
    }


def normalize_remembered_payments(
    payments: list[dict[str, object]],
) -> list[dict[str, object]]:
    normalized_payments = []
    for payment in payments:
        try:
            amount = round(float(payment.get("amount", 0.0)), 2)
        except (TypeError, ValueError):
            continue

        if amount > 0:
            normalized_payments.append(
                {
                    "amount": amount,
                    "saved_on": str(payment.get("saved_on", "")),
                }
            )

    return sorted(
        normalized_payments,
        key=lambda payment: (float(payment["amount"]), str(payment["saved_on"])),
    )


def normalize_recurring_extra_payments(
    payments: list[dict[str, int | float]],
) -> list[dict[str, int | float]]:
    normalized_payments = {}
    for payment in payments:
        try:
            normalized_payment = build_recurring_extra_payment(
                float(payment["target_payment"]),
                float(payment["amount"]),
                int(payment["start_month"]),
                int(payment["start_year"]),
            )
        except (KeyError, TypeError, ValueError):
            continue

        normalized_payments[recurring_extra_key(normalized_payment)] = normalized_payment

    return [
        normalized_payments[key]
        for key in sorted(normalized_payments)
    ]


def canonical_schedule_settings(
    settings: dict[str, object],
    today: date,
) -> dict[str, object]:
    try:
        payment_amounts = parse_payment_amounts(
            saved_text(settings, "payment_amounts_raw", "")
        )
    except ValueError:
        payment_amounts = []

    return {
        "current_balance": round(
            saved_float(settings, "current_balance", 250_000.0),
            2,
        ),
        "monthly_interest_rate_percent": round(
            saved_float(settings, "monthly_interest_rate_percent", 0.50),
            6,
        ),
        "escrow_payment": round(saved_float(settings, "escrow_payment", 0.0), 2),
        "is_mortgage_loan": saved_bool(settings, "is_mortgage_loan", False),
        "payment_amounts": [round(amount, 2) for amount in payment_amounts],
        "max_months": saved_int(settings, "max_months", 360, 12, 600),
        "start_month": saved_int(settings, "start_month", today.month, 1, 12),
        "start_year": saved_int(settings, "start_year", today.year, 1900, 2300),
        "remembered_extra_payments": normalize_remembered_payments(
            saved_remembered_payments(settings)
        ),
        "recurring_extra_payments": normalize_recurring_extra_payments(
            saved_recurring_extra_payments(settings)
        ),
    }


def schedule_inputs_changed(
    current_settings: dict[str, object],
    saved_settings: dict[str, object],
    today: date,
) -> bool:
    return canonical_schedule_settings(
        current_settings,
        today,
    ) != canonical_schedule_settings(saved_settings, today)


def build_amortization_schedule(
    starting_balance: float,
    monthly_interest_rate: float,
    total_monthly_payment: float,
    escrow_payment: float,
    recurring_extra_payments: list[dict[str, int | float]],
    start_date: date,
    max_months: int = 600,
) -> tuple[pd.DataFrame, AmortizationSummary]:
    monthly_payment = total_monthly_payment - escrow_payment
    recurring_extra_payment = sum(
        float(payment["amount"]) for payment in recurring_extra_payments
    )
    recurring_extra_start_date = min(
        (
            date(int(payment["start_year"]), int(payment["start_month"]), 1)
            for payment in recurring_extra_payments
        ),
        default=None,
    )
    balance = starting_balance
    total_interest = 0.0
    total_escrow = 0.0
    total_paid = 0.0
    total_recurring_extra = 0.0
    interest_paid_this_month = 0.0
    principal_paid_this_month = 0.0
    escrow_paid_this_month = 0.0
    recurring_extra_paid_this_month = 0.0
    total_paid_this_month = 0.0
    rows: list[dict[str, object]] = []

    def add_schedule_row(month: int, row_date: date) -> None:
        rows.append(
            {
                "Month": month,
                "Date": row_date,
                "Monthly Payment": f"${total_monthly_payment:,.2f}",
                "Principal + Interest Payment": round(max(0.0, monthly_payment), 2),
                "Balance Due": round(balance, 2),
                "Interest Paid": round(total_interest, 2),
                "Interest Paid This Month": round(interest_paid_this_month, 2),
                "Principal Paid This Month": round(principal_paid_this_month, 2),
                "Escrow Payment": round(escrow_paid_this_month, 2),
                "Additional Recurring Payment": round(
                    recurring_extra_paid_this_month,
                    2,
                ),
                "Total Monthly Payment": round(total_paid_this_month, 2),
            }
        )

    initial_balance_date = add_months(start_date, -1)
    add_schedule_row(0, initial_balance_date)

    if total_monthly_payment <= 0:
        return pd.DataFrame(rows), AmortizationSummary(
            monthly_payment=0.0,
            escrow_payment=escrow_payment,
            total_monthly_payment=total_monthly_payment,
            recurring_extra_payment=recurring_extra_payment,
            recurring_extra_start_date=recurring_extra_start_date,
            total_recurring_extra_paid=0.0,
            months_to_payoff=None,
            final_payment_date=None,
            total_interest_paid=0.0,
            total_escrow_paid=0.0,
            total_paid=0.0,
            final_balance=starting_balance,
            status="Payment must be greater than zero.",
        )

    if monthly_payment <= 0:
        return pd.DataFrame(rows), AmortizationSummary(
            monthly_payment=0.0,
            escrow_payment=escrow_payment,
            total_monthly_payment=total_monthly_payment,
            recurring_extra_payment=recurring_extra_payment,
            recurring_extra_start_date=recurring_extra_start_date,
            total_recurring_extra_paid=0.0,
            months_to_payoff=None,
            final_payment_date=None,
            total_interest_paid=0.0,
            total_escrow_paid=0.0,
            total_paid=0.0,
            final_balance=starting_balance,
            status="Total payment must be greater than escrow payment.",
        )

    payment_number = 0
    payment_date = start_date
    for payment_number in range(1, max_months + 1):
        payment_date = add_months(start_date, payment_number - 1)
        interest_for_month = balance * monthly_interest_rate
        scheduled_extra_payment = sum(
            float(payment["amount"])
            for payment in recurring_extra_payments
            if payment_date
            >= date(int(payment["start_year"]), int(payment["start_month"]), 1)
        )
        payment_available_for_loan = monthly_payment + scheduled_extra_payment
        principal_payment = payment_available_for_loan - interest_for_month

        if principal_payment <= 0:
            return pd.DataFrame(rows), AmortizationSummary(
                monthly_payment=monthly_payment,
                escrow_payment=escrow_payment,
                total_monthly_payment=total_monthly_payment,
                recurring_extra_payment=recurring_extra_payment,
                recurring_extra_start_date=recurring_extra_start_date,
                total_recurring_extra_paid=total_recurring_extra,
                months_to_payoff=None,
                final_payment_date=None,
                total_interest_paid=total_interest,
                total_escrow_paid=total_escrow,
                total_paid=total_paid,
                final_balance=balance,
                status="Payment after escrow does not cover monthly interest.",
            )

        actual_payment = min(payment_available_for_loan, balance + interest_for_month)
        interest_paid_this_month = interest_for_month
        principal_paid_this_month = actual_payment - interest_for_month
        escrow_paid_this_month = escrow_payment
        recurring_extra_paid_this_month = max(0.0, actual_payment - monthly_payment)
        total_paid_this_month = actual_payment + escrow_payment
        total_interest += interest_for_month
        total_escrow += escrow_payment
        total_recurring_extra += recurring_extra_paid_this_month
        total_paid += total_paid_this_month
        balance = max(0.0, balance + interest_for_month - actual_payment)
        add_schedule_row(payment_number, payment_date)

        if balance <= 0:
            break

    paid_off = balance <= 0
    return pd.DataFrame(rows), AmortizationSummary(
        monthly_payment=monthly_payment,
        escrow_payment=escrow_payment,
        total_monthly_payment=total_monthly_payment,
        recurring_extra_payment=recurring_extra_payment,
        recurring_extra_start_date=recurring_extra_start_date,
        total_recurring_extra_paid=total_recurring_extra,
        months_to_payoff=payment_number if paid_off else None,
        final_payment_date=payment_date if paid_off else None,
        total_interest_paid=total_interest,
        total_escrow_paid=total_escrow,
        total_paid=total_paid,
        final_balance=balance,
        status="Paid off" if paid_off else f"Not paid off within {max_months} months.",
    )


def money(value: float) -> str:
    return f"${value:,.2f}"


def percent(value: float) -> str:
    return f"{value:.1%}"


def add_current_marker(fig: go.Figure, start_date: date) -> None:
    fig.add_shape(
        type="line",
        x0=start_date,
        x1=start_date,
        y0=0,
        y1=1,
        xref="x",
        yref="paper",
        line={"color": "#444444", "dash": "dash", "width": 2},
    )
    fig.add_annotation(
        x=start_date,
        y=1,
        xref="x",
        yref="paper",
        text="First payment",
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
    )


def add_final_payment_markers(fig: go.Figure, schedules: pd.DataFrame, y_column: str) -> None:
    final_points = schedules[schedules["Balance Due"].eq(0)].groupby("Monthly Payment").head(1)
    if final_points.empty:
        return

    final_points = final_points.copy()
    final_points["Final Payment Amount"] = final_points["Total Monthly Payment"].map(
        money
    )

    fig.add_trace(
        go.Scatter(
            x=final_points["Date"],
            y=final_points[y_column],
            customdata=final_points[["Final Payment Amount"]],
            text=final_points["Monthly Payment"] + " final",
            hovertemplate="Final payment: %{customdata[0]}<extra></extra>",
            mode="markers+text",
            name="Final payment",
            textposition="top center",
            marker={"size": 9, "symbol": "diamond", "color": "#111827"},
        )
    )


def request_schedule_switch() -> None:
    st.session_state["pending_schedule_name"] = st.session_state.get(
        "schedule_selector"
    )


def main() -> None:
    st.set_page_config(page_title="Amortization Line Graph Calculator", layout="wide")

    st.title("Amortization Line Graph Calculator")
    update_message = st.session_state.pop("update_message", "")
    if update_message:
        st.success(f"Update installed. {update_message}")

    saved_settings = load_settings()
    saved_schedules = get_saved_schedules(saved_settings)
    schedule_names = sorted(saved_schedules)
    default_schedule_name = get_last_schedule_name(saved_settings, schedule_names)

    if (
        "active_schedule_name" not in st.session_state
        or st.session_state["active_schedule_name"] not in schedule_names
    ):
        st.session_state["active_schedule_name"] = (
            default_schedule_name or DEFAULT_SCHEDULE_NAME
        )

    if "pending_schedule_name" not in st.session_state:
        st.session_state["pending_schedule_name"] = None

    selected_schedule_name = st.session_state["active_schedule_name"]
    pending_schedule_name = st.session_state["pending_schedule_name"]
    if (
        schedule_names
        and pending_schedule_name is None
        and st.session_state.get("schedule_selector") != selected_schedule_name
    ):
        st.session_state["schedule_selector"] = selected_schedule_name

    active_settings = (
        saved_schedules[selected_schedule_name]
        if selected_schedule_name in saved_schedules
        else {}
    )
    remembered_extra_payments = saved_remembered_payments(active_settings)
    recurring_extra_payments = saved_recurring_extra_payments(active_settings)

    today = date.today()
    default_start_month = saved_int(active_settings, "start_month", today.month, 1, 12)
    default_start_year = saved_int(active_settings, "start_year", today.year, 1900, 2300)
    temporary_one_time_payment = float(
        st.session_state.get("temporary_one_time_payment", 0.0)
    )

    with st.sidebar:
        render_update_checker()

        with st.expander("Saved Payment Schedules", expanded=True):
            if schedule_names:
                st.selectbox(
                    "Load payment schedule",
                    schedule_names,
                    index=schedule_names.index(selected_schedule_name),
                    key="schedule_selector",
                    on_change=request_schedule_switch,
                )
                pending_schedule_name = st.session_state.get("pending_schedule_name")
                if pending_schedule_name == selected_schedule_name:
                    st.session_state["pending_schedule_name"] = None
                    pending_schedule_name = None

                if st.button("Delete Selected Schedule", use_container_width=True):
                    save_settings(
                        delete_named_schedule(saved_settings, selected_schedule_name)
                    )
                    st.success(f"Deleted {selected_schedule_name}.")
                    st.rerun()
            else:
                selected_schedule_name = DEFAULT_SCHEDULE_NAME
                st.caption("No saved schedules yet.")

            switch_prompt_container = st.container()

            save_schedule_name = st.text_input(
                "Save schedule name",
                value=selected_schedule_name or DEFAULT_SCHEDULE_NAME,
            )

        with st.expander("Loan Inputs", expanded=True):
            current_balance = st.number_input(
                "Current loan balance",
                min_value=0.0,
                value=saved_float(active_settings, "current_balance", 250_000.0),
                step=1_000.0,
                format="%.2f",
            )
            monthly_interest_rate_percent = st.number_input(
                "Effective monthly interest rate (%)",
                min_value=0.0,
                value=saved_float(
                    active_settings,
                    "monthly_interest_rate_percent",
                    0.50,
                ),
                step=0.000001,
                format="%.6f",
            )
            is_mortgage_loan = st.checkbox(
                "Is this a mortgage loan?",
                value=saved_bool(active_settings, "is_mortgage_loan", False),
            )
            if is_mortgage_loan:
                escrow_payment = st.number_input(
                    "Recurring monthly escrow payment",
                    min_value=0.0,
                    value=saved_float(active_settings, "escrow_payment", 0.0),
                    step=50.0,
                    format="%.2f",
                )
            else:
                escrow_payment = 0.0
            payment_amounts_raw = st.text_area(
                "Total monthly payment amounts, including escrow",
                value=saved_text(
                    active_settings,
                    "payment_amounts_raw",
                    "1500, 2000, 2500",
                ),
                help="Enter multiple values separated by commas or new lines.",
            )
            max_months = st.slider(
                "Maximum months to chart",
                12,
                600,
                saved_int(active_settings, "max_months", 360, 12, 600),
                12,
            )

        with st.expander("First Payment Date", expanded=True):
            start_month_name = st.selectbox(
                "First payment month",
                MONTHS,
                index=default_start_month - 1,
            )
            start_month = MONTHS.index(start_month_name) + 1
            start_year = st.number_input(
                "First payment year",
                min_value=1900,
                max_value=2300,
                value=default_start_year,
                step=1,
            )

        try:
            sidebar_payment_amounts = parse_payment_amounts(payment_amounts_raw)
        except ValueError:
            sidebar_payment_amounts = []

        active_recurring_extra_payments = list(recurring_extra_payments)
        with st.expander(
            recurring_extra_header(recurring_extra_payments),
            expanded=False,
        ):
            for recurring_payment in recurring_extra_payments:
                recurring_key = recurring_extra_key(recurring_payment)
                edit_payment = st.checkbox(
                    f"Edit {recurring_extra_label(recurring_payment)}",
                    value=False,
                    key=f"edit_recurring_{recurring_key}",
                )

                if edit_payment:
                    target_options = sorted(
                        set(
                            sidebar_payment_amounts
                            + [float(recurring_payment["target_payment"])]
                        )
                    )
                    target_index = target_options.index(
                        float(recurring_payment["target_payment"])
                    )
                    month_index = int(recurring_payment["start_month"]) - 1

                    with st.form(f"edit_recurring_form_{recurring_key}"):
                        keep_saved_recurring_payment = st.checkbox(
                            "Save this recurring payment",
                            value=True,
                        )
                        edited_recurring_amount = st.number_input(
                            "Recurring additional payment",
                            min_value=0.0,
                            value=float(recurring_payment["amount"]),
                            step=50.0,
                            format="%.2f",
                        )
                        edited_recurring_target = st.selectbox(
                            "Apply to total monthly payment",
                            target_options,
                            index=target_index,
                            format_func=money,
                        )
                        edited_recurring_start_month_name = st.selectbox(
                            "Recurring payment start month",
                            MONTHS,
                            index=month_index,
                        )
                        edited_recurring_start_month = (
                            MONTHS.index(edited_recurring_start_month_name) + 1
                        )
                        edited_recurring_start_year = st.number_input(
                            "Recurring payment start year",
                            min_value=1900,
                            max_value=2300,
                            value=int(recurring_payment["start_year"]),
                            step=1,
                        )
                        apply_recurring_edit = st.form_submit_button(
                            "Apply Changes",
                            use_container_width=True,
                        )

                    if apply_recurring_edit:
                        active_recurring_extra_payments = [
                            payment
                            for payment in active_recurring_extra_payments
                            if recurring_extra_key(payment) != recurring_key
                        ]

                        if keep_saved_recurring_payment:
                            if edited_recurring_amount <= 0:
                                st.info(
                                    "Enter a recurring payment greater than zero, "
                                    "or clear the save checkbox to remove it."
                                )
                                st.stop()

                            active_recurring_extra_payments.append(
                                build_recurring_extra_payment(
                                    edited_recurring_target,
                                    edited_recurring_amount,
                                    edited_recurring_start_month,
                                    int(edited_recurring_start_year),
                                )
                            )

                        active_recurring_extra_payments = list(
                            {
                                recurring_extra_key(payment): payment
                                for payment in active_recurring_extra_payments
                            }.values()
                        )
                        save_settings(
                            save_named_schedule(
                                saved_settings,
                                selected_schedule_name,
                                build_settings(
                                    current_balance,
                                    monthly_interest_rate_percent,
                                    escrow_payment,
                                    is_mortgage_loan,
                                    payment_amounts_raw,
                                    max_months,
                                    start_month,
                                    int(start_year),
                                    remembered_extra_payments,
                                    active_recurring_extra_payments,
                                ),
                            )
                        )
                        st.success(
                            "Recurring payment updated."
                            if keep_saved_recurring_payment
                            else "Recurring payment removed."
                        )
                        st.rerun()

            with st.form("recurring_extra_payment_form", clear_on_submit=True):
                recurring_extra_amount = st.number_input(
                    "New recurring additional payment",
                    min_value=0.0,
                    value=0.0,
                    step=50.0,
                    format="%.2f",
                )
                recurring_payment_target = st.selectbox(
                    "Apply to total monthly payment",
                    sidebar_payment_amounts if sidebar_payment_amounts else [0.0],
                    format_func=money,
                    disabled=not sidebar_payment_amounts,
                )
                recurring_start_month_name = st.selectbox(
                    "Recurring payment start month",
                    MONTHS,
                    index=start_month - 1,
                )
                recurring_start_month = MONTHS.index(recurring_start_month_name) + 1
                recurring_start_year = st.number_input(
                    "Recurring payment start year",
                    min_value=1900,
                    max_value=2300,
                    value=int(start_year),
                    step=1,
                )
                add_recurring_payment = st.form_submit_button(
                    "Add Recurring Payment",
                    use_container_width=True,
                    disabled=not sidebar_payment_amounts,
                )

            if add_recurring_payment:
                if recurring_extra_amount <= 0:
                    st.info("Enter a recurring payment greater than zero.")
                else:
                    active_recurring_extra_payments.append(
                        build_recurring_extra_payment(
                            recurring_payment_target,
                            recurring_extra_amount,
                            recurring_start_month,
                            int(recurring_start_year),
                        )
                    )
                    active_recurring_extra_payments = list(
                        {
                            recurring_extra_key(payment): payment
                            for payment in active_recurring_extra_payments
                        }.values()
                    )
                    save_settings(
                        save_named_schedule(
                            saved_settings,
                            save_schedule_name,
                            build_settings(
                                current_balance,
                                monthly_interest_rate_percent,
                                escrow_payment,
                                is_mortgage_loan,
                                payment_amounts_raw,
                                max_months,
                                start_month,
                                int(start_year),
                                remembered_extra_payments,
                                active_recurring_extra_payments,
                            ),
                        )
                    )
                    st.success("Recurring payment added.")
                    st.rerun()

        with st.expander("One-Time Balance Payments", expanded=False):
            remembered_extra_total = sum(
                float(payment["amount"]) for payment in remembered_extra_payments
            )
            if remembered_extra_total:
                st.caption(f"Remembered payments: {money(remembered_extra_total)}")

            with st.form("one_time_payment_form", clear_on_submit=True):
                one_time_payment = st.number_input(
                    "One-time additional balance payment",
                    min_value=0.0,
                    value=0.0,
                    step=100.0,
                    format="%.2f",
                )
                remember_one_time_payment = st.checkbox("Remember this payment")
                apply_one_time_payment = st.form_submit_button(
                    "Apply One-Time Payment",
                    use_container_width=True,
                )

            if apply_one_time_payment:
                if one_time_payment <= 0:
                    st.info("Enter a one-time payment greater than zero.")
                elif remember_one_time_payment:
                    remembered_extra_payments.append(
                        {
                            "amount": one_time_payment,
                            "saved_on": today.isoformat(),
                        }
                    )
                    save_settings(
                        save_named_schedule(
                            saved_settings,
                            save_schedule_name,
                            build_settings(
                                current_balance,
                                monthly_interest_rate_percent,
                                escrow_payment,
                                is_mortgage_loan,
                                payment_amounts_raw,
                                max_months,
                                start_month,
                                int(start_year),
                                remembered_extra_payments,
                                active_recurring_extra_payments,
                            ),
                        )
                    )
                    st.success("One-time payment remembered.")
                    st.rerun()
                else:
                    st.session_state["temporary_one_time_payment"] = one_time_payment
                    temporary_one_time_payment = one_time_payment
                    st.success("One-time payment applied to this session.")

            if temporary_one_time_payment:
                st.caption(
                    f"Temporary payment applied: {money(temporary_one_time_payment)}"
                )
                if st.button("Clear Temporary Payment", use_container_width=True):
                    st.session_state["temporary_one_time_payment"] = 0.0
                    st.rerun()

            if remembered_extra_payments and st.button(
                "Clear Remembered Payments",
                use_container_width=True,
            ):
                remembered_extra_payments = []
                save_settings(
                    save_named_schedule(
                        saved_settings,
                        save_schedule_name,
                        build_settings(
                            current_balance,
                            monthly_interest_rate_percent,
                            escrow_payment,
                            is_mortgage_loan,
                            payment_amounts_raw,
                            max_months,
                            start_month,
                            int(start_year),
                            remembered_extra_payments,
                            active_recurring_extra_payments,
                        ),
                    )
                )
                st.success("Remembered one-time payments cleared.")
                st.rerun()

        effective_starting_balance = max(
            0.0,
            current_balance - remembered_extra_total - temporary_one_time_payment,
        )
        st.caption(f"Balance used in graph: {money(effective_starting_balance)}")

        current_schedule_settings = build_settings(
            current_balance,
            monthly_interest_rate_percent,
            escrow_payment,
            is_mortgage_loan,
            payment_amounts_raw,
            max_months,
            start_month,
            int(start_year),
            remembered_extra_payments,
            active_recurring_extra_payments,
        )

        if st.button("Save Inputs", use_container_width=True):
            clean_schedule_name = normalize_schedule_name(save_schedule_name)
            save_settings(
                save_named_schedule(
                    saved_settings,
                    clean_schedule_name,
                    current_schedule_settings,
                )
            )
            st.success(f"Inputs saved under {clean_schedule_name}.")

        with switch_prompt_container:
            pending_schedule_name = st.session_state.get("pending_schedule_name")
            if (
                pending_schedule_name
                and pending_schedule_name != selected_schedule_name
                and pending_schedule_name in saved_schedules
            ):
                inputs_changed = schedule_inputs_changed(
                    current_schedule_settings,
                    active_settings,
                    today,
                )
                if not inputs_changed:
                    updated_settings = dict(saved_settings)
                    updated_settings["last_schedule_name"] = pending_schedule_name
                    save_settings(updated_settings)
                    st.session_state["active_schedule_name"] = pending_schedule_name
                    st.session_state["pending_schedule_name"] = None
                    st.session_state["temporary_one_time_payment"] = 0.0
                    st.rerun()
                else:
                    st.warning(
                        "Save the current schedule inputs before loading "
                        f"{pending_schedule_name}?"
                    )
                    save_switch_col, switch_col, cancel_col = st.columns(3)

                    with save_switch_col:
                        save_and_switch = st.button(
                            "Save and Switch",
                            use_container_width=True,
                        )
                    with switch_col:
                        switch_without_saving = st.button(
                            "Switch Without Saving",
                            use_container_width=True,
                        )
                    with cancel_col:
                        cancel_switch = st.button("Cancel", use_container_width=True)

                    if save_and_switch:
                        updated_settings = save_named_schedule(
                            saved_settings,
                            selected_schedule_name,
                            current_schedule_settings,
                        )
                        updated_settings["last_schedule_name"] = pending_schedule_name
                        save_settings(updated_settings)
                        st.session_state["active_schedule_name"] = pending_schedule_name
                        st.session_state["pending_schedule_name"] = None
                        st.session_state["temporary_one_time_payment"] = 0.0
                        st.rerun()

                    if switch_without_saving:
                        updated_settings = dict(saved_settings)
                        updated_settings["last_schedule_name"] = pending_schedule_name
                        save_settings(updated_settings)
                        st.session_state["active_schedule_name"] = pending_schedule_name
                        st.session_state["pending_schedule_name"] = None
                        st.session_state["temporary_one_time_payment"] = 0.0
                        st.rerun()

                    if cancel_switch:
                        st.session_state["pending_schedule_name"] = None
                        st.rerun()

    try:
        payment_amounts = parse_payment_amounts(payment_amounts_raw)
    except ValueError:
        st.error("Please enter valid payment amounts separated by commas or new lines.")
        st.stop()

    if current_balance <= 0:
        st.info("Enter a current loan balance greater than zero.")
        st.stop()

    if effective_starting_balance <= 0:
        st.info("The one-time balance payments fully cover the current loan balance.")
        st.stop()

    if not payment_amounts:
        st.info("Enter at least one total monthly payment amount.")
        st.stop()

    monthly_interest_rate = monthly_interest_rate_percent / 100
    start_date = date(int(start_year), start_month, 1)

    schedules: list[pd.DataFrame] = []
    summaries: list[AmortizationSummary] = []

    for payment in payment_amounts:
        payment_recurring_extras = recurring_extras_for_payment(
            active_recurring_extra_payments,
            payment,
        )
        schedule, summary = build_amortization_schedule(
            effective_starting_balance,
            monthly_interest_rate,
            payment,
            escrow_payment,
            payment_recurring_extras,
            start_date,
            max_months=max_months,
        )
        schedules.append(schedule)
        summaries.append(summary)

    all_schedules = pd.concat(schedules, ignore_index=True)

    balance_tab, interest_tab, payment_tab = st.tabs(
        ["Balance Due", "Interest Paid", "Total Monthly Payment"]
    )

    with balance_tab:
        balance_fig = px.line(
            all_schedules,
            x="Date",
            y="Balance Due",
            color="Monthly Payment",
            title="Balance Due Over Time",
        )
        add_current_marker(balance_fig, start_date)
        add_final_payment_markers(balance_fig, all_schedules, "Balance Due")
        balance_fig.update_layout(yaxis_tickprefix="$", hovermode="x unified")
        st.plotly_chart(balance_fig, use_container_width=True)

    with interest_tab:
        interest_fig = px.line(
            all_schedules,
            x="Date",
            y="Interest Paid",
            color="Monthly Payment",
            title="Cumulative Interest Paid Over Time",
        )
        add_current_marker(interest_fig, start_date)
        add_final_payment_markers(interest_fig, all_schedules, "Interest Paid")
        interest_fig.update_layout(yaxis_tickprefix="$", hovermode="x unified")
        st.plotly_chart(interest_fig, use_container_width=True)

    with payment_tab:
        payment_fig = px.line(
            all_schedules,
            x="Date",
            y="Total Monthly Payment",
            color="Monthly Payment",
            title="Total Monthly Payment Over Time",
        )
        add_current_marker(payment_fig, start_date)
        add_final_payment_markers(payment_fig, all_schedules, "Total Monthly Payment")
        payment_fig.update_layout(yaxis_tickprefix="$", hovermode="x unified")
        st.plotly_chart(payment_fig, use_container_width=True)

    with st.expander("Monthly Payment Breakdown"):
        breakdown = all_schedules[
            [
                "Date",
                "Monthly Payment",
                "Principal + Interest Payment",
                "Principal Paid This Month",
                "Interest Paid This Month",
                "Escrow Payment",
                "Additional Recurring Payment",
                "Total Monthly Payment",
                "Balance Due",
            ]
        ].copy()
        breakdown["Date"] = pd.to_datetime(breakdown["Date"]).dt.strftime("%b %Y")
        st.dataframe(
            breakdown,
            hide_index=True,
            use_container_width=True,
        )

    summary_rows = [
        {
            "Total Monthly Payment": money(summary.total_monthly_payment),
            "Escrow Payment": money(summary.escrow_payment),
            "Principal + Interest Payment": money(summary.monthly_payment),
            "Additional Recurring Payment": money(summary.recurring_extra_payment),
            "Recurring Payment Starts": format_month_year(
                summary.recurring_extra_start_date
            ),
            "Months to Payoff": summary.months_to_payoff
            if summary.months_to_payoff is not None
            else "N/A",
            "Remaining Payment Period": format_period(summary.months_to_payoff),
            "Final Payment Date": format_month_year(summary.final_payment_date),
            "Total Interest Paid": money(summary.total_interest_paid),
            "Total Escrow Paid": money(summary.total_escrow_paid),
            "Total Additional Recurring Paid": money(
                summary.total_recurring_extra_paid
            ),
            "Total Paid": money(summary.total_paid),
            "Final Balance": money(summary.final_balance),
            "Status": summary.status,
        }
        for summary in summaries
    ]

    st.subheader("Total Interest Paid")
    st.dataframe(
        pd.DataFrame(summary_rows),
        hide_index=True,
        use_container_width=True,
    )

    baseline_summary = next(
        (summary for summary in summaries if summary.monthly_payment > 0),
        summaries[0],
    )
    baseline_interest = baseline_summary.total_interest_paid

    comparison_rows = []
    for summary in summaries:
        interest_saved = baseline_interest - summary.total_interest_paid
        percent_saved = interest_saved / baseline_interest if baseline_interest else 0.0
        comparison_rows.append(
            {
                "Total Monthly Payment": money(summary.total_monthly_payment),
                "Principal + Interest Payment": money(summary.monthly_payment),
                "Additional Recurring Payment": money(summary.recurring_extra_payment),
                "Compared To": money(baseline_summary.total_monthly_payment),
                "Interest Saved": money(max(0.0, interest_saved)),
                "Percent Saved": percent(max(0.0, percent_saved)),
            }
        )

    st.subheader("Interest Saved Compared With Lowest Payment")
    st.dataframe(
        pd.DataFrame(comparison_rows),
        hide_index=True,
        use_container_width=True,
    )


if __name__ == "__main__":
    main()
