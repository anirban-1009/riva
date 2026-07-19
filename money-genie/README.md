# money-genie

## Purpose

The `money-genie` package is responsible for personal finance management, budgeting, expense tracking, cash flow forecasting, and financial advice workflows.

## Responsibilities

- **Expense Tracking & Categorization**: Importing, parsing, and classifying transactions.
- **Budget Management**: Setting, tracking, and adjusting budget limits for different categories.
- **Cash Flow Forecasting**: Projecting future income and expenses to estimate savings.
- **Financial Goal Planning**: Assisting users in tracking progress toward savings, debt payoff, or investment targets.
- **Financial Recommendations**: Delivering personalized insights on spending patterns and saving opportunities.

## Dependencies

- `common`

## Package Structure

```text
src/
└── money_genie/
    ├── __init__.py
    ├── models.py
    ├── services.py
    ├── tools.py
    ├── prompts.py
    └── plugin.py
```

## Running

```bash
uv run --package money-genie python -m money_genie
```

## Notes

This package should remain independent of other Genie packages. Any shared functionality should be moved into `common`.
