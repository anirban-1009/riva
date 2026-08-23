# Professional Code of Conduct and Design Standards

This document establishes the mandatory standards for all code written within the Job Hunt Mindmap project. The goal is to ensure long-term maintainability, readability, and extensibility.

## 1. Core Principles

### 1.1 Object-Oriented Programming (OOP)
- **Classes First**: All major logic must be encapsulated within classes. Avoid standalone script files.
- **Inheritance vs Composition**: Prefer composition over deep inheritance hierarchies. Use inheritance only when there is a clear "is-a" relationship and behavior is being extended.
- **Interfaces/Absractions**: Use Python's `abc.ABC` to define clear interfaces for components that may have multiple implementations (e.g., `JobSource`, `ResumeParser`, `NotificationService`).

### 1.2 SOLID Principles
- **S - Single Responsibility**: A class should have only one reason to change. Separate data ingestion from processing, and processing from presentation.
- **O - Open/Closed**: Classes should be open for extension but closed for modification. Use Strategy patterns to support new resume formats or job boards without rewriting core logic.
- **L - Liskov Substitution**: Subclasses must be interchangeable with their base classes without breaking the application.
- **I - Interface Segregation**: Clients should not be forced to depend on interfaces they do not use. Keep interfaces focused.
- **D - Dependency Inversion**: Depend upon abstractions, not concretions. Inject dependencies (like configuration or service clients) via `__init__` rather than instantiating them inside the class.

### 1.3 Modularity
- **Package Structure**: Maintain clear boundaries between `src.ingest`, `src.core`, `src.generator`, and `src.utils`.
- **Public API**: Use `__all__` in `__init__.py` files to explicitly define the public interface of a module.
- **Imports**: Avoid circular dependencies.

## 2. Professional Coding Standards

### 2.1 Style & Formatting
- **PEP 8**: Adhere strictly to PEP 8 standards. Used `ruff` or `black` for auto-formatting.
- **Type Hinting**: All function signatures must include type hints (`def process(self, data: Dict[str, Any]) -> bool:`).
- **Docstrings**: All classes and public methods must have Google-style docstrings describing arguments, return values, and exceptions.
- **Data Classes**: When a function returns multiple values, use a `dataclass` or `TypedDict` instead of a tuple or dictionary. This improves type safety and readability.

### 2.2 Error Handling
- **Exceptions**: Use **Custom Exception Classes** (e.g., `ResumeParsingError`, `LinkedInAPIError`) in `src.utils.exceptions` rather than generic `Exception` or `ValueError`.
- **Inheritance**: All custom exceptions should inherit from a base `MindMapError`.
- **Fail Fast**: Validate inputs early.
- **Logging**: Do not use `print()`. Use the central logger:
  ```python
  from src.utils.logger import get_logger
  logger = get_logger(__name__)
  logger.info("...")
  ```

### 2.3 Testing & Quality Assurance
- **Unit Tests**: Every public method MUST have corresponding unit tests.
- **Coverage**: Aim for maximum coverage (minimum 80%). Use `pytest-cov` to verify.
- **CI/CD**: All Pull Requests must pass the automated test suite via GitHub Actions before merging.
- **Class-Based Tests**: Organize tests into test classes (`class TestResumeParser:`) rather than loose functions.
- **Mocks**: External services and I/O MUST be mocked. Use `unittest.mock` or `pytest-mock`.
- **Determinism**: Tests must never rely on live network calls or external state.
- **Structure**: The `tests` folder structure must mirror the `src` project structure (e.g., `src/ingest/parser.py` -> `tests/ingest/test_parser.py`).

### 2.4 Package Management
- **Tool**: Always use `uv` for package management.
- **Python Execution**: Always use `uv run python` to run scripts or access the python interpreter (e.g. `uv run python -m src.main`). This ensures the correct environment and dependencies are used.
- **Commands**:
  - Install dependencies: `uv sync`
  - Add dependency: `uv add <package>`
  - Run tests: `uv run pytest`
- **Avoid Pip**: Do not use `pip install` directly unless absolutely necessary. Fix dependency issues via `uv`.

## 3. Extensibility Checklist
Before finalizing a module, ask:
1.  _Can I add a new job board (e.g., Indeed) without touching the LinkedIn scraper code?_
2.  _Can I swap the LLM provider (Gemini -> Ollama) by changing only configuration?_
3.  _Is the resume parsing logic decoupled from the file format (PDF vs DOCX)?_

## 4. Code Review Guidelines
- **No Magic Numbers/Strings**: Move constants to `src.utils.constants` or configuration.
- **Variable Naming**: Use descriptive, intention-revealing names. `job_list` is better than `l`.
- **Commit Messages**: specific and descriptive (e.g., `feat: implement PDF parsing strategy`, not `update parser`).
