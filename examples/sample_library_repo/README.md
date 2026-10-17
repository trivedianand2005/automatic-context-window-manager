# LibTrack (ACWM test repository)

A small library management system: a book catalog, members, loans with due dates,
renewals, late fees, member e-mails and usage reports. Standard library only, with dummy
data only.

## Layout

- `libtrack/catalog.py`: books and search
- `libtrack/members.py`: member registry
- `libtrack/loans.py`: checkout, return, renew, overdue
- `libtrack/fines.py`: late fee calculation
- `libtrack/notifications.py`: member e-mails
- `libtrack/reports.py`: monthly usage statistics
- `libtrack/storage.py`: JSON persistence
- `libtrack/config.py`: policy settings (loan days, fee per day, limits)
- `libtrack/cli.py`: command-line interface
- `tests/`: pytest suite

## Run the tests

```bash
cd examples/sample_library_repo
python -m pytest
```
