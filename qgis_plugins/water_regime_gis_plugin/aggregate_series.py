from __future__ import annotations

from collections import defaultdict
from statistics import mean, median


def average_by_date(rows, date_key: str, value_keys, group_keys=(), field_key="field_id"):
    """Median duplicate field observations, then average fields for each date."""
    per_field = defaultdict(lambda: defaultdict(list))
    for row in rows:
        date = row.get(date_key)
        field = row.get(field_key)
        if not date or not field:
            continue
        key = tuple(row.get(column) for column in group_keys) + (date, field)
        for column in value_keys:
            try:
                per_field[key][column].append(float(row[column]))
            except (KeyError, TypeError, ValueError):
                continue

    by_date = defaultdict(lambda: defaultdict(list))
    for key, values in per_field.items():
        for column, numbers in values.items():
            if numbers:
                by_date[key[:-1]][column].append(median(numbers))

    result = []
    for key in sorted(by_date):
        row = dict(zip((*group_keys, date_key), key))
        row.update({column: mean(numbers) for column, numbers in by_date[key].items()})
        result.append(row)
    return result
