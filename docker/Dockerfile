FROM python:3.11-slim

RUN apt-get update && apt-get install -y unzip && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.zip .
RUN unzip main.zip -d . && rm main.zip

EXPOSE 7778

CMD ["python", "app.py"]
