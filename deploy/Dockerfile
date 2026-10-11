FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app/kit
RUN pip install --no-cache-dir /app/kit
# Put your unzipped pack in ./pack and your agent.json next to this file; mount them at run time.
VOLUME ["/data"]
EXPOSE 8787
CMD ["speakvora-pack-agent", "run", "-c", "/data/agent.json"]
