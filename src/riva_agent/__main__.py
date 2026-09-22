import uvicorn


def main() -> None:
    """Run the Riva Agent AI gateway with uvicorn, matching the Dockerfile's CMD."""
    uvicorn.run("riva_agent.api.gateway:app", host="0.0.0.0", port=8085)


if __name__ == "__main__":
    main()
