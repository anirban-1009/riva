## v1.1.0 (2026-10-02)

### Feat

- add provider environment variable overrides, robust Ollama capability parsing, and build script registry options

## v1.0.0 (2026-10-02)

### Feat

- add passive memory candidate staging, conversational recency replay, and profile show/edit commands
- add pr-description workflow to draft and open pull requests
- introduce chat session management with CLI and API endpoints
- add database telemetry, vacuum, backup, and prune capabilities with CLI support
- add test-audit skill and update project dependencies

### Fix

- resolve gateway model ID issue and refine intelligence reasoning heuristics
- resolve gateway model ID issue and refine intelligence reasoning heuristics
- **lint**: pin ruff isort first-party packages and align pre-commit ruff version

### Refactor

- update gateway tests to use async httpx client fixture

## v0.2.1 (2026-09-24)

### Feat

- add pr-description skill and update workspace dependency documentation
- implement SQLite-based episodic memory and profile stores with tests and configuration updates
- add CLI, laya memory router configuration, and storage test suites
- add profile and episodic memory stores and integrate Riva assistant mode
- add spaCy model auto-download fallback and memory store evaluation notebook
- implement memory router module and add corresponding tests
- support flexible thinking parameters and concise instruction injection in Ollama provider
- add sync_docs.sh script and update development timeline link in README
- add LLMProvider protocol and OpenAI-compatible provider
- add spaCy-based thinking router notebook for query complexity analysis
- Add mem0 setup notebook and dependencies
- add documentation for PR description generation and inference latency investigation
- integrate commitizen for versioning and changelog generation; update build script for improved release process

## v0.2.0 (2026-07-26)

### Feat

- update version to 0.1.1 and enhance build script for streamlined release process with changelog generation
- enhance OllamaProvider with capabilities caching and extended thinking heuristic; update API gateway for improved chat handling and logging
- refactor chat completion handling and introduce new data models for structured responses
- implement Docker support with Dockerfile and docker-compose, add build script, and enhance OllamaProvider for improved streaming and error handling
- **llm**: implement OpenAI-compatible API gateway and add httpx-based asynchronous streaming to Ollama provider
- **llm**: create central AI LLM gateway and OllamaProvider for local models

### Fix

- add .DS_Store to .gitignore to prevent tracking of macOS system files
