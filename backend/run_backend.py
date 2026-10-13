import uvicorn

APP_IMPORT_PATH = "app.main:app"
EVENT_LOOP_FACTORY = "app.event_loop:create_psycopg_compatible_event_loop"


def main() -> None:
    uvicorn.run(
        APP_IMPORT_PATH,
        host="127.0.0.1",
        port=8000,
        loop=EVENT_LOOP_FACTORY,
    )


if __name__ == "__main__":
    main()
