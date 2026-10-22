# NEBULA CI/CD setup

## Pipeline behavior
- Pull requests and pushes to `main`/`master`: install dependencies, syntax check, run pytest, and build the Docker image.
- Pushes to `main`: after tests pass, log in to Docker Hub and publish `latest` plus a commit-SHA tag.

## GitHub setup
1. Create a GitHub repository and push the contents of this `nebula` folder. Ensure `.github/workflows/ci-cd.yml` is included.
2. In Docker Hub, create a repository named `nebula-weather` and create an access token.
3. In GitHub repository Settings -> Secrets and variables -> Actions, add repository secrets:
   - `DOCKERHUB_USERNAME`: your Docker Hub username
   - `DOCKERHUB_TOKEN`: the Docker Hub access token (not your account password)
4. Push to the `main` branch. Open the Actions tab to watch the workflow.

The Docker Hub publishing job only runs on `main` and only after tests and the image build pass. Do not commit `.env` or API keys.

## Local validation
From this folder run:
```bash
python -m pip install -r requirements.txt pytest
python -m py_compile app.py
pytest -q
docker compose up --build -d
```
