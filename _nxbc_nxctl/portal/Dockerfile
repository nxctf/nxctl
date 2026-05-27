FROM python:3.12-slim

WORKDIR /workspace

COPY portal/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

CMD ["uvicorn", "portal.app:app", "--host", "0.0.0.0", "--port", "8080"]
