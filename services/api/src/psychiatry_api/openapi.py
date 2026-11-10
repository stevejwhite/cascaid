import json
import sys

if __name__ == "__main__":
    from psychiatry_api.config import Settings
    from psychiatry_api.main import create_app

    # Contracts describe every development route, including the opt-in case editor, and do
    # not depend on the local .env file.
    app = create_app(Settings(_env_file=None, authoring_enabled=True))
    sys.stdout.write(json.dumps(app.openapi(), indent=2) + "\n")
