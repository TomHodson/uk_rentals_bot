# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm
WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY src src

CMD ["python3", "src/scrape.py"]