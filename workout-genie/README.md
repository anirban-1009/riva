# workout-genie

## Purpose

The `workout-genie` package is responsible for health and fitness coaching, workout routine generation, workout tracking, nutrition planning, and wellness analysis workflows.

## Responsibilities

- **Workout Planning**: Generating tailored exercise programs based on fitness goals, experience, and equipment.
- **Activity & Metric Tracking**: Logging completed exercises, sets, reps, and physical metrics.
- **Nutrition & Diet Coaching**: Planning meals, calculating caloric/macronutrient needs, and logging food intake.
- **Progress Insights**: Analyzing workout and biometric trends over time.
- **Exercise Demos & Curation**: Providing guidance on proper exercise forms and safety tips.

## Dependencies

- `common`

## Package Structure

```text
src/
└── workout_genie/
    ├── __init__.py
    ├── models.py
    ├── services.py
    ├── tools.py
    ├── prompts.py
    └── plugin.py
```

## Running

```bash
uv run --package workout-genie python -m workout_genie
```

## Notes

This package should remain independent of other Genie packages. Any shared functionality should be moved into `common`.
