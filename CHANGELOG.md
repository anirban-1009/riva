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
